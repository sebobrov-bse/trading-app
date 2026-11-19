"""GerchikFalseBreakout — Ложный пробой через висящий Stop-ордер.

Datas:
    datas[0] = M1 (primary, source for resampling)
    datas[1] = M5 (resampled from M1) — next() runs here
    datas[2] = D1 (separate feed, context)

Timeline (same as breakout, but:
- direction is derived from level vs price: level > close -> SHORT,
  level < close -> LONG. No trend/path filter (ЛП — reversal pattern).
- cancellation priority: level_reclaimed > moved_away > expired.
- tail_too_large -> FALLBACK to calculated_stop (not skip).

Why level_reclaimed is highest priority:
    ЛП = 'breakout failed and reversed'. If price re-claims the level
    in the breakout direction (close > level for SHORT), the reversal
    thesis is dead — exit immediately, even if Setup hasn't expired.
"""

import logging
from datetime import date, datetime, timedelta

import pandas as pd

from app.strategies.base import BaseStrategy
from app.strategies.gerchik.config import GerchikConfig
from app.strategies.gerchik.false_breakout import (
    FalseBreakoutSetup,
    detect_false_breakout,
)
from app.strategies.gerchik.m1_stop_timing import check_stop_order_trigger
from app.strategies.gerchik.room_to_move import (
    check_room_to_move,
    find_next_level,
)

logger = logging.getLogger(__name__)


class GerchikFalseBreakout(BaseStrategy):
    """Gerchik 'false breakout' strategy: reversal on failed breakout."""

    # ---- Metadata ----
    name = "gerchik_false_breakout"
    display_name = "Герчик: Ложный пробой"
    description = "Пробой хвостом + возврат за уровень + Stop-ордер"
    tags = ["gerchik", "false_breakout", "reversal", "intraday"]
    intraday_only = True
    direction = {"long": True, "short": True}
    default_risk_config = {
        "risk_per_trade_pct": 0.25,
    }

    params = (
        ("symbol", "SBER"),
        ("levels_cache", None),
        ("system_config", None),
        # ЛП: DISTRIBUTION + (ACCUMULATION/COMPRESSION if fb_allow_after_failed=True)
        ("allowed_energy", ("distribution", "accumulation", "compression")),
    )

    def __init__(self) -> None:
        super().__init__()
        self.cfg: GerchikConfig = self.p.system_config or GerchikConfig()
        self.days_cache: dict[date, object] = self.p.levels_cache or {}

        self.m1_data = self.datas[0]
        self.m5_data = self.datas[1] if len(self.datas) > 1 else None
        self.d1_data = self.datas[2] if len(self.datas) > 2 else None

        # Per-day state
        self.current_date: date | None = None
        self.trend: str = "NEUTRAL"
        self.atr: float = 0.0
        self.prev_close: float = 0.0
        self.path_ratio: float = 0.0
        self.strong_levels: list = []

        # Active setup
        self.active_setup: FalseBreakoutSetup | None = None
        self.setup_bars_since_detect: int = 0
        self._setup_energy: str = ""
        self._setup_score: int = 0

        # Entry state
        self._entry_pattern_meta: dict | None = None
        self._target_price: float | None = None
        self._target_direction: str | None = None
        self._entry_m5_dt: datetime | None = None
        self._closing: bool = False
        self._cooldown_until: datetime | None = None
        self._last_m5_dt: datetime | None = None

        # Diagnostics (NOT self.stats)
        self.counters = {
            "setups_detected": 0,
            "triggered": 0,
            "cancelled_expired": 0,
            "cancelled_moved_away": 0,
            "cancelled_level_reclaimed": 0,
            "skipped_by_tail": 0,
            "skipped_by_room": 0,
            "fallback_used": 0,
            "skipped_by_energy": 0,
        }

    # ------------------------------------------------------------------
    #  Main loop
    # ------------------------------------------------------------------

    def next(self) -> None:
        super().next()
        if self.m5_data is None or len(self.m5_data) < 3:
            return

        m5_dt = self.m5_data.datetime.datetime(0)
        if self._last_m5_dt == m5_dt:
            return
        self._last_m5_dt = m5_dt

        m5_date = m5_dt.date()
        if self.current_date != m5_date:
            self._update_day(m5_date)

        if self.position:
            self._manage_position(m5_dt)
            return

        if self.active_setup is not None:
            self._manage_active_setup(m5_dt)
            return

        self._try_detect_setup(m5_dt)

    # ------------------------------------------------------------------
    #  Day update
    # ------------------------------------------------------------------

    def _update_day(self, m5_date: date) -> None:
        self.current_date = m5_date
        self.active_setup = None
        self.setup_bars_since_detect = 0

        day = self.days_cache.get(m5_date)
        if day is None:
            self.trend = "NEUTRAL"
            self.atr = 0.0
            self.strong_levels = []
            return

        self.trend = day.trend
        self.atr = day.atr
        self.prev_close = day.prev_close
        self.path_ratio = day.path_ratio

        if self.atr > 0 and self.prev_close > 0:
            day_low = self.prev_close - 2.0 * self.atr
            day_high = self.prev_close + 2.0 * self.atr
        else:
            day_low, day_high = 0.0, 1e9

        self.strong_levels = [
            r
            for r in day.rows
            if r.energy.value in self.p.allowed_energy and day_low <= r.level_price <= day_high
        ]

    # ------------------------------------------------------------------
    #  Setup detection
    # ------------------------------------------------------------------

    def _try_detect_setup(self, m5_dt: datetime) -> None:
        if self.current_date is None:
            return
        if self._cooldown_until is not None:
            if m5_dt < self._cooldown_until:
                return
            self._cooldown_until = None

        if not self.strong_levels:
            self.counters["skipped_by_energy"] += 1
            return

        # Session end: no new setups after.
        session_end = (
            self.cfg.session_end_evening
            if self.cfg.use_evening_session
            else self.cfg.session_end_main
        )
        end_h, end_m = map(int, session_end.split(":"))
        if (m5_dt.hour, m5_dt.minute) >= (end_h, end_m):
            return

        m5_df = self._build_m5_df(n=5)
        if m5_df is None or len(m5_df) < 2:
            return

        last_close = float(self.m5_data.close[-1])

        for row in self.strong_levels:
            # Direction: from level vs current price.
            # level > close -> price below -> false UP breakout -> SHORT.
            # level < close -> price above -> false DOWN breakout -> LONG.
            if row.level_price > last_close:
                direction = "SHORT"
            elif row.level_price < last_close:
                direction = "LONG"
            else:
                continue

            setup = detect_false_breakout(
                m5_df,
                row.level_price,
                direction,
                row.energy.value,
                row.total_score,
                self.cfg,
            )
            if setup is None:
                continue

            # Override bar indices to global scale.
            setup.detected_at_bar = len(self.m5_data)
            setup.expires_at_bar = setup.detected_at_bar + self.cfg.fb_max_wait_bars

            self.active_setup = setup
            self.setup_bars_since_detect = 0
            self._setup_energy = row.energy.value
            self._setup_score = row.total_score
            self.counters["setups_detected"] += 1
            self.log(
                f"SETUP {direction} level={row.level_price:.2f} "
                f"pattern={setup.pattern} "
                f"stop_order={setup.stop_order_price:.4f} "
                f"tail={setup.tail_size:.4f} reason={setup.setup_reason}"
            )
            return

    def _build_m5_df(self, n: int = 5) -> pd.DataFrame | None:
        """Last N CLOSED M5 bars."""
        if self.m5_data is None or len(self.m5_data) < n + 1:
            return None
        rows = []
        for offset in range(-n, 0):
            rows.append(
                {
                    "timestamp": self.m5_data.datetime.datetime(offset),
                    "open": float(self.m5_data.open[offset]),
                    "high": float(self.m5_data.high[offset]),
                    "low": float(self.m5_data.low[offset]),
                    "close": float(self.m5_data.close[offset]),
                }
            )
        return pd.DataFrame(rows)

    # ------------------------------------------------------------------
    #  Active setup management
    # ------------------------------------------------------------------

    def _manage_active_setup(self, m5_dt: datetime) -> None:
        setup = self.active_setup
        if setup is None:
            return

        self.setup_bars_since_detect += 1

        last_close = float(self.m5_data.close[-1])

        # --- Cancel #1: level_reclaimed (highest priority) ---
        # SHORT: price went back ABOVE level -> false breakout thesis broken.
        # LONG:  price went back BELOW level -> broken.
        if setup.direction == "SHORT" and last_close > setup.level:
            self.counters["cancelled_level_reclaimed"] += 1
            self.log(f"CANCEL level_reclaimed SHORT level={setup.level:.2f} close={last_close:.4f}")
            self.active_setup = None
            self._cooldown_until = m5_dt + timedelta(minutes=30)
            return
        if setup.direction == "LONG" and last_close < setup.level:
            self.counters["cancelled_level_reclaimed"] += 1
            self.log(f"CANCEL level_reclaimed LONG level={setup.level:.2f} close={last_close:.4f}")
            self.active_setup = None
            self._cooldown_until = m5_dt + timedelta(minutes=30)
            return

        # --- Cancel #2: expired ---
        if self.setup_bars_since_detect > self.cfg.fb_max_wait_bars:
            self.counters["cancelled_expired"] += 1
            self.log(f"CANCEL expired {setup.direction} level={setup.level:.2f}")
            self.active_setup = None
            self._cooldown_until = m5_dt + timedelta(minutes=30)
            return

        # --- Cancel #3: moved_away ---
        distance = abs(last_close - setup.level)
        threshold = self.cfg.fb_cancel_distance * setup.calculated_stop_size
        if distance > threshold:
            self.counters["cancelled_moved_away"] += 1
            self.log(
                f"CANCEL moved_away {setup.direction} level={setup.level:.2f} dist={distance:.4f}"
            )
            self.active_setup = None
            self._cooldown_until = m5_dt + timedelta(minutes=30)
            return

        # Skip trigger on detection bar.
        if self.setup_bars_since_detect < 1:
            return

        m1_bars = self._collect_m1_in_last_closed_m5()
        if not m1_bars:
            return

        triggered, fill = check_stop_order_trigger(
            setup,
            m1_bars,
            mode=self.cfg.fb_m1_mode,
        )
        if not triggered:
            return

        self._execute_trigger(setup, fill, m5_dt)

    def _collect_m1_in_last_closed_m5(self) -> list[dict]:
        if len(self.m5_data) < 2:
            return []
        bpu2_dt = self.m5_data.datetime.datetime(-1)
        m5_start = bpu2_dt - timedelta(minutes=5)

        m1_bars: list[dict] = []
        for i in range(len(self.m1_data)):
            m1_dt = self.m1_data.datetime.datetime(-i)
            if m1_dt >= bpu2_dt:
                continue
            if m1_dt < m5_start:
                break
            m1_bars.insert(
                0,
                {
                    "open": float(self.m1_data.open[-i]),
                    "high": float(self.m1_data.high[-i]),
                    "low": float(self.m1_data.low[-i]),
                    "close": float(self.m1_data.close[-i]),
                },
            )
        return m1_bars

    # ------------------------------------------------------------------
    #  Trigger execution
    # ------------------------------------------------------------------

    def _execute_trigger(
        self,
        setup: FalseBreakoutSetup,
        fill_price: float,
        m5_dt: datetime,
    ) -> None:
        tail = setup.tail_size
        luff = setup.calculated_stop_size * self.cfg.luff_ratio
        technical_stop = tail + luff

        # KEY DIFFERENCE from breakout: fallback, not skip.
        if technical_stop > setup.calculated_stop_size:
            if self.cfg.fb_stop_fallback_to_calculated:
                stop_size = setup.calculated_stop_size
                self.counters["fallback_used"] += 1
                self.log(
                    f"FALLBACK stop {setup.direction} level={setup.level:.2f} "
                    f"tail={tail:.4f} tech={technical_stop:.4f} "
                    f"using={stop_size:.4f}"
                )
            else:
                self.counters["skipped_by_tail"] += 1
                self.log(
                    f"SKIP tail_too_large {setup.direction} "
                    f"level={setup.level:.2f} tail={tail:.4f} "
                    f"tech={technical_stop:.4f}"
                )
                self.active_setup = None
                self._cooldown_until = m5_dt + timedelta(minutes=30)
                return
        else:
            stop_size = technical_stop

        entry = fill_price
        if setup.direction == "LONG":
            stop_price = entry - stop_size
            commission = entry * self.cfg.commission_rate * 2
            tp_price = entry + 3 * stop_size + commission
        else:
            stop_price = entry + stop_size
            commission = entry * self.cfg.commission_rate * 2
            tp_price = entry - 3 * stop_size - commission

        # Room to move.
        level_prices = [r.level_price for r in self.strong_levels]
        next_level = find_next_level(
            setup.level,
            "long" if setup.direction == "LONG" else "short",
            level_prices,
        )
        if not check_room_to_move(entry, stop_size, next_level, self.cfg):
            self.counters["skipped_by_room"] += 1
            self.log(
                f"SKIP insufficient_room {setup.direction} "
                f"level={setup.level:.2f} entry={entry:.4f} "
                f"next={next_level}"
            )
            self.active_setup = None
            self._cooldown_until = m5_dt + timedelta(minutes=30)
            return

        self.counters["triggered"] += 1
        self._entry_pattern_meta = {
            "pattern": "false_breakout",
            "level_score": self._setup_score,
            "energy": self._setup_energy,
            "path_ratio": self.path_ratio,
        }
        self._entry_m5_dt = m5_dt
        self._closing = False
        # Logical TP (checked in _manage_position) instead of TP order.
        # Prevents race condition between safe_close's cancel(tp) and
        # TP fill (phantom position -> fake bt.pnl).
        self._target_price = tp_price
        self._target_direction = setup.direction

        self.safe_buy(
            direction="long" if setup.direction == "LONG" else "short",
            custom_stop=stop_price,
            # NOT passing custom_tp -> no TP order -> no phantom.
        )

        self.log(
            f"TRIGGERED {setup.direction} level={setup.level:.2f} "
            f"fill={entry:.4f} stop={stop_price:.4f} tp={tp_price:.4f} "
            f"tail={tail:.4f} stop_size={stop_size:.4f}"
        )

        self.active_setup = None
        self._cooldown_until = m5_dt + timedelta(minutes=30)

    # ------------------------------------------------------------------
    #  Position management
    # ------------------------------------------------------------------

    def _manage_position(self, m5_dt: datetime) -> None:
        if not self.position:
            self._closing = False
            self._target_price = None
            self._target_direction = None
            return

        # Logical TP: check M5 close against target.
        if self._target_price is not None and self._target_direction is not None:
            last_close = float(self.m5_data.close[-1])
            hit_tp = False
            if self._target_direction == "LONG" and last_close >= self._target_price:
                hit_tp = True
            elif self._target_direction == "SHORT" and last_close <= self._target_price:
                hit_tp = True
            if hit_tp:
                if not self._closing:
                    self._closing = True
                    self.safe_close()
                    self.log(
                        f"EXIT target_hit {self._target_direction} "
                        f"close={last_close:.4f} target={self._target_price:.4f}"
                    )
                return

        session_end = (
            self.cfg.session_end_evening
            if self.cfg.use_evening_session
            else self.cfg.session_end_main
        )
        end_h, end_m = map(int, session_end.split(":"))
        if (m5_dt.hour, m5_dt.minute) >= (end_h, end_m):
            if not self._closing:
                self._closing = True
                self.safe_close()
                self.log(f"EXIT session_end {session_end}")
            return

    # ------------------------------------------------------------------
    #  Trade log enrichment
    # ------------------------------------------------------------------

    def notify_trade(self, trade) -> None:
        meta = self._entry_pattern_meta
        super().notify_trade(trade)
        if trade.isclosed and meta is not None and self.trade_log:
            self.trade_log[-1].update(meta)
            self._entry_pattern_meta = None
