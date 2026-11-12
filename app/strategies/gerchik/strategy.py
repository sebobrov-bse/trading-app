"""GerchikSystem — full trading strategy for S.2b.5.

Combines precomputed D1 context (precompute_gerchik) with M1 timing:

Per D1 bar D:
  1. skip if PrecomputedDay absent for D (weekend, holiday, or warmup)
  2. skip if trend == NEUTRAL
  3. skip if |path_ratio| < min_path_ratio
  4. direction from trend (UP -> long, DOWN -> short)
  5. filter strong levels: energy in allowed_energy AND level on
     the correct side of close
  6. load M1 bars for D (cached); for each candidate level, ask
     find_entry_signal for a pattern; first enter_* wins -> safe_buy
  7. one entry attempt per day (_tried_date)

Exit:
  - stop order (from M1 EntryDecision.stop_price)
  - time-based: close after max_hold_days calendar days

Entry timing: buy() in next() fills at D+1 open. No look-ahead.
"""

import logging
from datetime import date, timedelta

import pandas as pd

from app.strategies.base import BaseStrategy
from app.strategies.gerchik.config import GerchikConfig
from app.strategies.gerchik.timing import find_entry_signal

logger = logging.getLogger(__name__)


class GerchikSystem(BaseStrategy):
    """Gerchik Market Profile strategy with M1 timing."""

    # ---- Metadata ----
    name = "gerchik"
    display_name = "Система Герчика"
    description = "Market Profile + M1 timing (bounce/breakout/limit_player)"
    tags = ["gerchik", "market_profile", "m1_timing"]
    direction = {"long": True, "short": True}
    intraday_only = False

    params = (
        ("symbol", "SBER"),
        ("levels_cache", None),
        ("system_config", None),
        ("pattern", "bounce"),
        ("direction_mode", "both"),
        ("max_hold_days", None),
        ("min_path_ratio", None),
        ("allowed_energy", ("distribution", "neutral")),
    )

    params_meta = [
        {
            "name": "pattern",
            "type": "str",
            "default": "bounce",
            "description": "bounce | breakout | limit_player",
        },
        {
            "name": "direction_mode",
            "type": "str",
            "default": "both",
            "description": "long | short | both",
        },
        {
            "name": "max_hold_days",
            "type": "int",
            "default": 3,
            "min": 1,
            "max": 30,
            "description": "Максимум дней в позиции",
        },
        {
            "name": "min_path_ratio",
            "type": "float",
            "default": 0.75,
            "min": 0.1,
            "max": 3.0,
            "description": "Минимальный |path_ratio|",
        },
        {
            "name": "allowed_energy",
            "type": "list",
            "default": ["distribution"],
            "description": "Какие энергии разрешены для входа",
        },
    ]

    def __init__(self) -> None:
        super().__init__()
        self.days_cache: dict[date, object] = self.p.levels_cache or {}
        self.cfg: GerchikConfig = self.p.system_config or GerchikConfig()
        self._entry_date: date | None = None
        self._tried_date: date | None = None
        self._m1_cache: dict[date, pd.DataFrame | None] = {}

    # ------------------------------------------------------------------
    #  Main loop
    # ------------------------------------------------------------------

    def next(self) -> None:
        # BaseStrategy.next -> _on_bar_start (risk + dynamic levels).
        super().next()

        if not self.position:
            self._entry_date = None
            self._try_enter()
        else:
            self._manage_position()

    # ------------------------------------------------------------------
    #  Entry logic
    # ------------------------------------------------------------------

    def _try_enter(self) -> None:
        current_dt = self.datas[0].datetime.datetime(0)
        current_date = current_dt.date()

        if self._tried_date == current_date:
            return
        self._tried_date = current_date

        day = self.days_cache.get(current_date)
        if day is None:
            logger.info("%s: no precomputed day", current_date)
            return
        logger.info(
            "%s: trend=%s path=%.2f close=%.2f", current_date, day.trend, day.path_ratio, day.close
        )

        # Gate 2: path_ratio threshold. Fall back to GerchikConfig if
        # params didn't override (None).
        threshold = (
            self.p.min_path_ratio
            if self.p.min_path_ratio is not None
            else self.cfg.system_min_path_ratio
        )
        if abs(day.path_ratio) < threshold:
            logger.info("%s: skip |path|=%.2f < %.2f", current_date, abs(day.path_ratio), threshold)
            return

        # Gate 3: direction. For NEUTRAL trend, use path_ratio as a
        # momentum fallback — but require a STRONG path (default 1.0 ATR).
        # This is not pure Gerchik (structure not confirmed) but is
        # defensible: price action is decisive, not a coin flip.
        if day.trend == "NEUTRAL":
            neutral_min = self.cfg.system_neutral_path_min
            if abs(day.path_ratio) < neutral_min:
                logger.info(
                    "%s: skip NEUTRAL + weak path (%.2f < %.2f)",
                    current_date,
                    abs(day.path_ratio),
                    neutral_min,
                )
                return
            direction = "long" if day.path_ratio > 0 else "short"
            logger.info(
                "%s: NEUTRAL fallback -> %s (|path|=%.2f)",
                current_date,
                direction,
                abs(day.path_ratio),
            )
        else:
            if self.p.direction_mode == "long" and day.trend != "UP":
                return
            if self.p.direction_mode == "short" and day.trend != "DOWN":
                return
            direction = "long" if day.trend == "UP" else "short"

        # Gate 4: filter levels by energy, side of close, and the bar's
        # actual high/low range. A level outside [low, high] was never
        # touched today, so M1 will return no_touch anyway. Not look-ahead:
        # current D1 bar is already closed, and the decision (order at D+1
        # open) is consistent with data available at next()-time.
        day_low = float(self.datas[0].low[0])
        day_high = float(self.datas[0].high[0])

        candidates = [
            r
            for r in day.rows
            if r.energy.value in self.p.allowed_energy
            and day_low <= r.level_price <= day_high
            and (
                (direction == "long" and r.level_price < day.close)
                or (direction == "short" and r.level_price > day.close)
            )
        ]
        if not candidates:
            logger.info(
                "%s: skip no candidates (dir=%s close=%.2f day=[%.2f, %.2f] levels=%d)",
                current_date,
                direction,
                day.close,
                day_low,
                day_high,
                len(day.rows),
            )
            return
        logger.info("%s: candidates=%d dir=%s", current_date, len(candidates), direction)

        # Load M1 bars for the day (cached).
        m1 = self._load_m1(current_date)
        if m1 is None or len(m1) == 0:
            return

        # Try candidates in price order: nearest to price first.
        if direction == "long":
            candidates.sort(key=lambda r: -r.level_price)  # highest first
        else:
            candidates.sort(key=lambda r: r.level_price)  # lowest first

        for row in candidates:
            dec = find_entry_signal(
                m1,
                row.level_price,
                direction,
                self.p.pattern,
                self.cfg,
            )
            logger.info(
                "%s: level=%.2f -> %s (%s)", current_date, row.level_price, dec.action, dec.reason
            )
            if dec.action not in ("enter_long", "enter_short"):
                continue

            if dec.stop_price is None:
                continue

            self.safe_buy(
                direction=direction,
                custom_stop=dec.stop_price,
            )
            self._entry_date = current_date
            self.log(
                f"ENTER {direction} level={row.level_price:.2f} "
                f"pattern={self.p.pattern} "
                f"m1_entry={dec.entry_price:.4f} "
                f"stop={dec.stop_price:.4f}"
            )
            return

    # ------------------------------------------------------------------
    #  Position management
    # ------------------------------------------------------------------

    def _manage_position(self) -> None:
        if self._entry_date is None:
            return
        current_date = self.datas[0].datetime.datetime(0).date()
        days_held = (current_date - self._entry_date).days
        max_hold = (
            self.p.max_hold_days
            if self.p.max_hold_days is not None
            else self.cfg.system_max_hold_days
        )
        if days_held >= max_hold:
            self.safe_close()
            self.log(f"EXIT time-based: held {days_held} days")
            self._entry_date = None

    # ------------------------------------------------------------------
    #  M1 data access
    # ------------------------------------------------------------------

    def _load_m1(self, day: date) -> pd.DataFrame | None:
        if day in self._m1_cache:
            return self._m1_cache[day]

        from app.db.session import SessionLocal
        from app.services.candle_repository import CandleRepository

        repo = CandleRepository()
        try:
            # get_dataframe excludes `end`; push +1 day to include `day`.
            load_end = day + timedelta(days=1)
            try:
                df = repo.get_dataframe(
                    symbol=self.p.symbol,
                    timeframe=1,
                    start=day,
                    end=load_end,
                )
            except TypeError:
                with SessionLocal() as db:
                    df = repo.get_dataframe(
                        db,
                        symbol=self.p.symbol,
                        timeframe=1,
                        start=day,
                        end=load_end,
                    )
        except Exception as exc:
            self.log(f"M1 load failed for {day}: {exc}")
            self._m1_cache[day] = None
            return None

        self._m1_cache[day] = df
        return df
