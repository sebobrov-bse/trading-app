"""GerchikRejection — БСУ/БПУ1/БПУ2 strategy.

Datas:
    datas[0] = M1 (primary, source for resampling)
    datas[1] = M5 (resampledata from M1) — next() runs here
    datas[2] = D1 (separate feed from candles timeframe=24)

Per M5 bar:
  1. On new day: load PrecomputedDay from levels_cache.
     Extract trend, atr, prev_close, path_ratio, distribution levels
     that are inside [D1.low, D1.high].
  2. If pending pattern -> check M1 fill inside the БПУ2 M5.
     FILLED -> safe_buy on next M5 open (market).
     NOT_FILLED / MODEL_BROKEN -> drop pending.
  3. If no pending and no position:
     - Gate: trend is UP/DOWN (from day.trend) -> direction.
     - Gate: |path_ratio| >= min_path_ratio (0.75 default).
     - Gate: optional entry time window.
     - For each distribution level: find_rejection_pattern on last N M5.
       First pattern with tp_price != None -> pending.
  4. If position: session-end close; timeout close.
"""

import logging
from datetime import date, datetime, timedelta

import pandas as pd

from app.strategies.base import BaseStrategy
from app.strategies.gerchik.config import GerchikConfig
from app.strategies.gerchik.rejection import (
    RejectionPattern,
    find_rejection_pattern,
)
from app.strategies.gerchik.m1_timing import check_m1_fill

logger = logging.getLogger(__name__)


class GerchikRejection(BaseStrategy):
    """Gerchik 'rejection' strategy with БСУ/БПУ1/БПУ2 and strict M1 timing."""

    # ---- Metadata ----
    name = "gerchik_rejection"
    display_name = "Герчик: Отбой от уровня"
    description = "БСУ/БПУ1/БПУ2 + strict M1-тайминг + энергия DISTRIBUTION"
    tags = ["gerchik", "rejection", "mean_reversion", "intraday"]
    intraday_only = True
    direction = {"long": True, "short": True}
    default_risk_config = {
        "risk_per_trade_pct": 0.25,
    }

    params = (
        ("symbol", "SBER"),
        ("levels_cache", None),
        ("system_config", None),
        ("max_m5_lookback", 20),
        ("allowed_energy", ("distribution", "neutral")),
    )

    def __init__(self) -> None:
        super().__init__()
        self.cfg: GerchikConfig = self.p.system_config or GerchikConfig()
        self.days_cache: dict[date, object] = self.p.levels_cache or {}

        # Datas order (see module docstring).
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

        # Pending / active trade
        self._entry_pattern: RejectionPattern | None = None
        self._entry_meta: dict | None = None
        self._closing: bool = False
        self._entry_m5_dt: datetime | None = None
        self._last_m5_dt: datetime | None = None

        # Diagnostics counters (read from outside after run).
        # NOTE: must NOT be named `stats` — Backtrader reserves
        # `self.stats` for observers (Broker, BuySell, Trades).
        self.counters = {
            "patterns_found": 0,
            "filled": 0,
            "not_filled": 0,
            "model_broken": 0,
            "skipped_by_energy": 0,
            "skipped_by_path": 0,
            "skipped_by_trend": 0,
            "skipped_by_room": 0,
        }

    # ------------------------------------------------------------------
    #  Main loop
    # ------------------------------------------------------------------

    def next(self) -> None:
        super().next()
        if self.m5_data is None or len(self.m5_data) < 2:
            return

        m5_dt = self.m5_data.datetime.datetime(0)

        if self._last_m5_dt == m5_dt:
            return
        self._last_m5_dt = m5_dt

        m5_date = m5_dt.date()

        if self.current_date != m5_date:
            self._update_day(m5_date)

        if not self.position:
            self._try_enter(m5_dt)
        else:
            self._manage_position(m5_dt)

    # ------------------------------------------------------------------
    #  Day update
    # ------------------------------------------------------------------

    def _update_day(self, m5_date: date) -> None:
        self.current_date = m5_date
        self._entry_pattern = None
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

        # Level filter range: close±2*ATR (NOT current D1 high/low —
        # that's look-ahead: at 10:00 we don't know the day's full high).
        # 2*ATR gives a reasonable "where price could reach today" zone.
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
    #  Entry: find pattern
    # ------------------------------------------------------------------

    def _try_enter(self, m5_dt: datetime) -> None:
        if self.current_date is None:
            return
        if not self.strong_levels:
            self.counters["skipped_by_energy"] += 1
            return

        # Path filter (trend/range regime).
        if abs(self.path_ratio) < self.cfg.atr_filter_threshold:
            self.counters["skipped_by_path"] += 1
            return

        # Direction: from trend. NEUTRAL fallback — if |path_ratio| is
        # strong enough (system_neutral_path_min, default 0.7), use the
        # path direction. Same logic as the old GerchikSystem — without
        # it, 13/19 June days are NEUTRAL and 0 patterns found.
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

        # Session end: no new entries after session_end.
        # Without this, _try_enter fires every M5 after 18:45, creating
        # a "enter -> close on next bar -> enter" loop.
        session_end = (
            self.cfg.session_end_evening
            if self.cfg.use_evening_session
            else self.cfg.session_end_main
        )
        end_h, end_m = map(int, session_end.split(":"))
        if (m5_dt.hour, m5_dt.minute) >= (end_h, end_m):
            return

        # Entry time filter (optional).
        if self.cfg.use_entry_time_filter and not self._in_entry_window(m5_dt):
            return

        m5_df = self._build_m5_df()
        if m5_df is None or len(m5_df) < 2:
            return

        level_prices = [r.level_price for r in self.strong_levels]
        for row in self.strong_levels:
            pat = find_rejection_pattern(
                m5_df,
                row.level_price,
                direction,
                level_prices,
                self.cfg,
            )
            if pat is None:
                continue
            if pat.tp_price is None:
                self.counters["skipped_by_room"] += 1
                continue
            self.counters["patterns_found"] += 1
            self.log(
                f"PATTERN {pat.direction} level={pat.level:.2f} "
                f"entry={pat.entry_price:.4f} stop={pat.stop_price:.4f} "
                f"tp={pat.tp_price:.4f}"
            )
            # Snapshot level metadata; attached to trade_log on close.
            self._entry_meta = {
                "pattern": "rejection",
                "level_score": row.total_score,
                "energy": row.energy.value,
                "path_ratio": self.path_ratio,
            }
            # Immediately check M1 fill inside the БПУ2 (M5 N-1).
            self._check_fill_and_execute(pat)
            return

    def _in_entry_window(self, dt: datetime) -> bool:
        s_h, s_m = map(int, self.cfg.entry_time_filter_start.split(":"))
        e_h, e_m = map(int, self.cfg.entry_time_filter_end.split(":"))
        t = (dt.hour, dt.minute)
        return (s_h, s_m) <= t <= (e_h, e_m)

    def _build_m5_df(self) -> pd.DataFrame | None:
        """The two last CLOSED M5 bars (BPU1, BPU2 candidates).

        Index 0 = M5 N (current, not closed). [-1] = M5 N-1, [-2] = M5 N-2.
        Pair (-2, -1) = (N-2, N-1) — the freshest closed pair.
        """
        if self.m5_data is None or len(self.m5_data) < 3:
            return None
        rows = []
        for offset in (-2, -1):
            rows.append(
                {
                    "timestamp": self.m5_data.datetime.datetime(offset),
                    "high": float(self.m5_data.high[offset]),
                    "low": float(self.m5_data.low[offset]),
                    "close": float(self.m5_data.close[offset]),
                }
            )
        return pd.DataFrame(rows)

    # ------------------------------------------------------------------
    #  Position management
    # ------------------------------------------------------------------

    def _check_fill_and_execute(self, pat: RejectionPattern) -> None:
        """Check M1 fill inside the БПУ2 (M5 N-1) and place order if FILLED.

        БПУ2 = second bar of the pattern = M5 N-1 ([-1] in backtrader
        notation relative to current M5 N).
        """
        bpu2_dt = self.m5_data.datetime.datetime(-1)
        m5_start = bpu2_dt - timedelta(minutes=5)

        # Collect M1 bars INSIDE the БПУ2 M5.
        # Backtrader: [0] = current (newest), [-1] = previous, ...
        # Iterate newest->oldest; skip M1 of the forming M5; stop at M5 start.
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
                    "high": float(self.m1_data.high[-i]),
                    "low": float(self.m1_data.low[-i]),
                    "close": float(self.m1_data.close[-i]),
                },
            )

        bpu2_bar = {
            "high": float(self.m5_data.high[-1]),
            "low": float(self.m5_data.low[-1]),
            "close": float(self.m5_data.close[-1]),
        }

        status, info = check_m1_fill(
            bpu2_bar,
            m1_bars,
            pat.level,
            pat.luff,
            pat.direction,
            self.cfg.m1_timing_mode,
        )

        if status == "FILLED":
            self.counters["filled"] += 1
            self.safe_buy(
                direction="long" if pat.direction == "LONG" else "short",
                custom_stop=pat.stop_price,
                custom_tp=pat.tp_price,
            )
            self._entry_pattern = pat
            self._entry_m5_dt = bpu2_dt
            self.log(
                f"FILLED {pat.direction} level={pat.level:.2f} "
                f"limit={pat.entry_price:.4f} m1_bars={len(m1_bars)}"
            )
        elif status == "MODEL_BROKEN":
            self.counters["model_broken"] += 1
            self.log(f"MODEL_BROKEN {pat.direction} level={pat.level:.2f}")
        else:
            self.counters["not_filled"] += 1
            self.log(f"NOT_FILLED {pat.direction} level={pat.level:.2f} m1_bars={len(m1_bars)}")

    def _manage_position(self, m5_dt: datetime) -> None:
        # Reset _closing when position is fully closed.
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
            # Guard against firing every bar between decision and fill:
            # close() takes 1 M5 to execute, but position is still truthy.
            if not getattr(self, "_closing", False):
                self._closing = True
                self.safe_close()
                self.log(f"EXIT session_end {session_end}")
            return

        if self.cfg.position_timeout_hours > 0 and self._entry_m5_dt is not None:
            elapsed_h = (m5_dt - self._entry_m5_dt).total_seconds() / 3600.0
            if elapsed_h >= self.cfg.position_timeout_hours:
                self.safe_close()
                self.log(f"EXIT timeout {elapsed_h:.1f}h")

    def notify_trade(self, trade) -> None:
        """Enrich the just-appended trade_log entry with rejection context."""
        meta = self._entry_meta
        super().notify_trade(trade)
        if trade.isclosed and meta is not None and self.trade_log:
            self.trade_log[-1].update(meta)
            self._entry_meta = None
