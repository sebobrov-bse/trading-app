"""GerchikBreakout — Пробой через висящий Stop-ордер.

Datas:
    datas[0] = M1 (primary, source for resampling)
    datas[1] = M5 (resampled from M1) — next() runs here
    datas[2] = D1 (separate feed, context + future-proofing)

Timeline:
    M5 N   : detect setup (based on last closed bar m5[-1]).
             Active setup stored. Order "live" from M5 N start.
    M5 N+1 : check trigger on M1 bars inside m5[-1] (= M5 N, now closed).
             If triggered -> safe_buy (fills at M5 N+2 open).
    M5 N+2 : position open; if strong_move, schedule post-entry confirm.
    M5 N+3 : check m5[-1].close (= M5 N+2, first closed after entry).

Cancel conditions:
    - setup_bars_since_detect > max_wait_bars (expired)
    - |close - level| > cancel_distance * calc_stop_size (moved_away)
    - level's energy becomes compression (v1.0: no-op, energy is per-day)

Post-entry confirm (only if strong_move_before):
    - m5[-1].close must be on the correct side of level.
    - Otherwise close immediately (safe_close).
"""

import logging
from datetime import date, datetime, timedelta

import pandas as pd

from app.strategies.base import BaseStrategy
from app.strategies.gerchik.breakout import (
    BreakoutSetup,
    detect_breakout_setup,
)
from app.strategies.gerchik.config import GerchikConfig
from app.strategies.gerchik.m1_stop_timing import check_stop_order_trigger
from app.strategies.gerchik.room_to_move import (
    check_room_to_move,
    find_next_level,
)

logger = logging.getLogger(__name__)


class GerchikBreakout(BaseStrategy):
    """Gerchik 'breakout' strategy: accumulation + pending Stop order."""

    # ---- Metadata ----
    name = "gerchik_breakout"
    display_name = "Герчик: Пробой уровня"
    description = "Аккумуляция + висящий Stop-ордер + M1-тайминг"
    tags = ["gerchik", "breakout", "trend", "intraday"]
    intraday_only = True
    direction = {"long": True, "short": True}
    default_risk_config = {"risk_per_trade_pct": 0.25}

    params = (
        ("symbol", "SBER"),
        ("levels_cache", None),
        ("system_config", None),
        ("allowed_energy", ("accumulation", "compression")),
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
        self.active_setup: BreakoutSetup | None = None
        self.setup_bars_since_detect: int = 0
        self._setup_energy: str = ""
        self._setup_score: int = 0

        # Entry / meta
        self._entry_pattern_meta: dict | None = None
        self._entry_m5_dt: datetime | None = None
        self._closing: bool = False
        self._cooldown_until: datetime | None = None
        self._last_m5_dt: datetime | None = None

        # Post-entry confirm for strong_move
        self._pending_confirm: bool = False
        self._confirm_at_m5_idx: int = 0
        self._entry_direction: str | None = None
        self._entry_level: float = 0.0
        self._entry_strong: bool = False

        # Diagnostics (NOT self.stats — backtrader reserves it)
        self.counters = {
            "setups_detected": 0,
            "triggered": 0,
            "confirmed": 0,
            "cancelled_expired": 0,
            "cancelled_moved_away": 0,
            "cancelled_compression": 0,
            "skipped_by_energy": 0,
            "skipped_by_path": 0,
            "skipped_by_trend": 0,
            "skipped_by_tail": 0,
            "skipped_by_room": 0,
            "skipped_by_confirm": 0,
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
            self._check_post_entry_confirm()
            return

        if self.active_setup is not None:
            self._manage_active_setup(m5_dt)
            if self.position:
                # Just triggered; skip confirm this bar.
                return
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

        # Direction: trend, NEUTRAL fallback by path_ratio.
        if self.trend == "UP":
            direction = "LONG"
        elif self.trend == "DOWN":
            direction = "SHORT"
        else:
            neutral_min = self.cfg.system_neutral_path_min
            if abs(self.path_ratio) < neutral_min:
                self.counters["skipped_by_trend"] += 1
                return
            direction = "LONG" if self.path_ratio > 0 else "SHORT"

        # Path filter.
        if abs(self.path_ratio) < self.cfg.atr_filter_threshold:
            self.counters["skipped_by_path"] += 1
            return

        # Session end: no new setups after end.
        session_end = (
            self.cfg.session_end_evening
            if self.cfg.use_evening_session
            else self.cfg.session_end_main
        )
        end_h, end_m = map(int, session_end.split(":"))
        if (m5_dt.hour, m5_dt.minute) >= (end_h, end_m):
            return

        m5_df = self._build_m5_df(n=self.cfg.breakout_strong_move_lookback)
        if m5_df is None or len(m5_df) < 3:
            return

        for row in self.strong_levels:
            setup = detect_breakout_setup(
                m5_df,
                row.level_price,
                direction,
                row.energy.value,
                self.atr,
                self.cfg,
            )
            if setup is None:
                continue

            # Override bar indices to global scale.
            setup.detected_at_bar = len(self.m5_data)
            setup.expires_at_bar = setup.detected_at_bar + self.cfg.breakout_max_wait_bars

            self.active_setup = setup
            self.setup_bars_since_detect = 0
            self._setup_energy = row.energy.value
            self._setup_score = row.total_score
            self.counters["setups_detected"] += 1
            self.log(
                f"SETUP {direction} level={row.level_price:.2f} "
                f"stop_order={setup.stop_order_price:.4f} "
                f"reason={setup.setup_reason} "
                f"strong={setup.strong_move_before}"
            )
            return

    def _build_m5_df(self, n: int = 10) -> pd.DataFrame | None:
        """Last N CLOSED M5 bars (ending at [-1])."""
        if self.m5_data is None or len(self.m5_data) < n + 1:
            return None
        rows = []
        for offset in range(-n, 0):  # -n, ..., -1
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
    #  Active setup: cancel + trigger check
    # ------------------------------------------------------------------

    def _manage_active_setup(self, m5_dt: datetime) -> None:
        setup = self.active_setup
        if setup is None:
            return

        self.setup_bars_since_detect += 1

        # Cancel: expired.
        if self.setup_bars_since_detect > self.cfg.breakout_max_wait_bars:
            self.counters["cancelled_expired"] += 1
            self.log(f"CANCEL expired {setup.direction} level={setup.level:.2f}")
            self.active_setup = None
            # Cooldown so we don't immediately re-detect the same level.
            self._cooldown_until = m5_dt + timedelta(minutes=30)
            return

        # Cancel: moved away (by last closed bar's close).
        if len(self.m5_data) >= 2:
            last_close = float(self.m5_data.close[-1])
            distance = abs(last_close - setup.level)
            threshold = self.cfg.breakout_cancel_distance * setup.calculated_stop_size
            if distance > threshold:
                self.counters["cancelled_moved_away"] += 1
                self.log(
                    f"CANCEL moved_away {setup.direction} "
                    f"level={setup.level:.2f} dist={distance:.4f}"
                )
                self.active_setup = None
                # Same cooldown: 30 min before trying again, otherwise
                # we re-detect the same level every bar (19 times on 06-26).
                self._cooldown_until = m5_dt + timedelta(minutes=30)
                return

        # Skip trigger check on the detection bar itself.
        # Order goes live "from next M5".
        if self.setup_bars_since_detect < 1:
            return

        # Check trigger on M1 bars inside the last CLOSED M5.
        m1_bars = self._collect_m1_in_last_closed_m5()
        if not m1_bars:
            return

        triggered, fill = check_stop_order_trigger(
            setup,
            m1_bars,
            mode=self.cfg.breakout_m1_mode,
        )
        if not triggered:
            return

        self._execute_trigger(setup, fill, m5_dt)

    def _collect_m1_in_last_closed_m5(self) -> list[dict]:
        """Collect M1 bars inside the last closed M5 (m5[-1])."""
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
    #  Trigger execution: tail + stop + tp + room + safe_buy
    # ------------------------------------------------------------------

    def _execute_trigger(
        self,
        setup: BreakoutSetup,
        fill_price: float,
        m5_dt: datetime,
    ) -> None:
        if len(self.m5_data) < 2:
            self.active_setup = None
            return

        last_m5_low = float(self.m5_data.low[-1])
        last_m5_high = float(self.m5_data.high[-1])

        if setup.direction == "LONG":
            tail = fill_price - last_m5_low
        else:
            tail = last_m5_high - fill_price

        if tail < 0:
            tail = 0.0  # gap fill beyond the bar's extreme

        luff = setup.calculated_stop_size * self.cfg.luff_ratio
        technical_stop_size = tail + luff

        # Tail too large -> skip.
        if technical_stop_size > setup.max_allowed_stop:
            self.counters["skipped_by_tail"] += 1
            self.log(
                f"SKIP tail_too_large {setup.direction} "
                f"level={setup.level:.2f} tail={tail:.4f} "
                f"tech={technical_stop_size:.4f} "
                f"max={setup.max_allowed_stop:.4f}"
            )
            self.active_setup = None
            return

        stop_size = technical_stop_size
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
            return

        # Execute.
        self.counters["triggered"] += 1
        self._entry_pattern_meta = {
            "pattern": "breakout",
            "level_score": self._setup_score,
            "energy": self._setup_energy,
            "path_ratio": self.path_ratio,
        }
        self._entry_direction = setup.direction
        self._entry_level = setup.level
        self._entry_strong = setup.strong_move_before
        self._entry_m5_dt = m5_dt
        self._closing = False

        self.safe_buy(
            direction="long" if setup.direction == "LONG" else "short",
            custom_stop=stop_price,
            custom_tp=tp_price,
        )

        self.log(
            f"TRIGGERED {setup.direction} level={setup.level:.2f} "
            f"fill={entry:.4f} stop={stop_price:.4f} tp={tp_price:.4f} "
            f"tail={tail:.4f}"
        )

        # Strong-move confirmation: check first closed M5 AFTER fill.
        # Fill happens on next M5 open -> check that bar's close on the
        # bar AFTER that. Schedule check for +2 M5s.
        if setup.strong_move_before:
            self._pending_confirm = True
            self._confirm_at_m5_idx = len(self.m5_data) + 2

        self.active_setup = None
        self._cooldown_until = m5_dt + timedelta(minutes=30)

    # ------------------------------------------------------------------
    #  Position management + post-entry confirm
    # ------------------------------------------------------------------

    def _manage_position(self, m5_dt: datetime) -> None:
        if not self.position:
            self._closing = False
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

    def _check_post_entry_confirm(self) -> None:
        if not self._pending_confirm:
            return
        if self.position.size == 0:
            return
        if len(self.m5_data) < self._confirm_at_m5_idx:
            return

        bar_close = float(self.m5_data.close[-1])

        if self._entry_direction == "LONG" and bar_close < self._entry_level:
            self.log(f"CONFIRM FAIL LONG close={bar_close:.4f} < level={self._entry_level:.4f}")
            self.counters["skipped_by_confirm"] += 1
            self.safe_close()
        elif self._entry_direction == "SHORT" and bar_close > self._entry_level:
            self.log(f"CONFIRM FAIL SHORT close={bar_close:.4f} > level={self._entry_level:.4f}")
            self.counters["skipped_by_confirm"] += 1
            self.safe_close()
        else:
            self.log(f"CONFIRM OK {self._entry_direction}")
            self.counters["confirmed"] += 1

        self._pending_confirm = False

    # ------------------------------------------------------------------
    #  Trade log enrichment
    # ------------------------------------------------------------------

    def notify_trade(self, trade) -> None:
        """Enrich trade_log[-1] with breakout meta."""
        meta = self._entry_pattern_meta
        super().notify_trade(trade)
        if trade.isclosed and meta is not None and self.trade_log:
            self.trade_log[-1].update(meta)
            self._entry_pattern_meta = None
