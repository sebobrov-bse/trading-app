"""Risk manager: state, limits, and decision-making during a backtest.

Sits between the strategy and the pure functions in `stops.py` /
`position_sizer.py`. Owns all mutable state (PnL counters, streak of
losses, day/week/month tracking).
"""

import logging
from datetime import date
from decimal import Decimal
from typing import Literal

import backtrader as bt
from sqlalchemy import select

from app.db.session import SessionLocal
from app.models.instrument_spec import InstrumentSpec
from app.risk.config import RiskConfig
from app.risk.position_sizer import calculate_size
from app.risk.stops import (
    calculate_stop_price as _stop_price,
    calculate_stop_distance as _stop_distance,
    calculate_take_profit_price as _tp_price,
)

logger = logging.getLogger(__name__)

Direction = Literal["long", "short"]


class RiskManager:
    """Per-strategy risk state and gatekeeper.

    Typical lifecycle:
    - __init__ once at strategy creation.
    - on_new_bar(date) at the start of every next().
    - can_open_position() before entering.
    - calculate_position_size() before entering.
    - calculate_stop_price() / calculate_take_profit_price() on entry.
    - on_trade_closed(pnl, rr) after a trade closes.
    - get_stats() at the end of the backtest.
    """

    def __init__(self, strategy: bt.Strategy, config: RiskConfig) -> None:
        self.strategy = strategy
        self.config = config

        # ---- cumulative PnL for limits ----
        self.daily_pnl: float = 0.0
        self.weekly_pnl: float = 0.0
        self.monthly_pnl: float = 0.0

        # ---- calendar anchors for resets ----
        self.current_date: date | None = None
        self.current_iso_week: tuple[int, int] | None = None  # (year, week)
        self.current_month: tuple[int, int] | None = None  # (year, month)

        # ---- activity counters ----
        self.trades_today: int = 0
        self.consecutive_losses: int = 0
        self.max_consecutive_losses: int = 0

        # ---- outcome counters ----
        self.stops_hit: int = 0
        self.take_profits_hit: int = 0

        # ---- skip reasons (for diagnostics) ----
        self.skipped_by_atr: int = 0
        self.skipped_by_daily_limit: int = 0
        self.skipped_by_weekly_limit: int = 0
        self.skipped_by_monthly_limit: int = 0
        self.skipped_by_max_positions: int = 0
        self.skipped_by_consecutive_losses: int = 0
        self.skipped_by_size_zero: int = 0
        self.skipped_by_direction: int = 0

        # ---- tracking for average risk metrics ----
        self._risk_pcts: list[float] = []  # realized risk per trade, %
        self._rr_realized: list[float] = []  # realized R multiples
        self._sizes_pct: list[float] = []  # position size as % of capital

        # ---- lazy-loaded contract multiplier (for futures) ----
        self._multiplier: Decimal | None = None
        self._multiplier_loaded: bool = False

    # ------------------------------------------------------------------
    #  Lifecycle hooks
    # ------------------------------------------------------------------

    def on_new_bar(self, bar_date: date) -> None:
        """Called at the start of every bar. Resets daily/weekly/monthly."""
        iso = bar_date.isocalendar()
        week_key = (iso[0], iso[1])
        month_key = (bar_date.year, bar_date.month)

        if self.current_date is None:
            # First bar — initialize anchors.
            self.current_date = bar_date
            self.current_iso_week = week_key
            self.current_month = month_key
            return

        if bar_date != self.current_date:
            # New day.
            self.current_date = bar_date
            self.daily_pnl = 0.0
            self.trades_today = 0
            # Reset loss streak — "3 losses in a row" applies per day,
            # not across the whole backtest.
            self.consecutive_losses = 0

        if week_key != self.current_iso_week:
            self.current_iso_week = week_key
            self.weekly_pnl = 0.0

        if month_key != self.current_month:
            self.current_month = month_key
            self.monthly_pnl = 0.0

    def on_trade_closed(
        self,
        pnl: float,
        realized_rr: float | None = None,
        risk_pct: float | None = None,
        size_pct: float | None = None,
    ) -> None:
        """Update PnL counters and streak after a trade closes.

        `realized_rr` — actual reward/risk multiple (optional).
        `risk_pct` — actual risk of this trade as % of capital (optional).
        `size_pct` — position size as % of capital (optional).
        """
        self.daily_pnl += pnl
        self.weekly_pnl += pnl
        self.monthly_pnl += pnl

        if pnl < 0:
            self.consecutive_losses += 1
            self.max_consecutive_losses = max(self.max_consecutive_losses, self.consecutive_losses)
        else:
            self.consecutive_losses = 0

        if realized_rr is not None:
            self._rr_realized.append(realized_rr)
        if risk_pct is not None:
            self._risk_pcts.append(risk_pct)
        if size_pct is not None:
            self._sizes_pct.append(size_pct)

    # ------------------------------------------------------------------
    #  Gatekeeper
    # ------------------------------------------------------------------

    def can_open_position(self, direction: Direction) -> tuple[bool, str]:
        """Return (allowed, reason). `reason` is 'ok' or a short code."""
        if not self.config.use_risk_management:
            return True, "risk_disabled"

        # Direction constraints.
        if direction == "long" and self.config.short_only:
            self.skipped_by_direction += 1
            return False, "short_only"
        if direction == "short" and self.config.long_only:
            self.skipped_by_direction += 1
            return False, "long_only"

        capital = self._get_capital()

        # Daily loss limit.
        if capital > 0 and self.daily_pnl < 0:
            daily_loss_pct = -self.daily_pnl / capital * 100.0
            if daily_loss_pct >= self.config.max_daily_loss_pct:
                self.skipped_by_daily_limit += 1
                return False, "daily_limit"

        # Weekly loss limit.
        if capital > 0 and self.weekly_pnl < 0:
            weekly_loss_pct = -self.weekly_pnl / capital * 100.0
            if weekly_loss_pct >= self.config.max_weekly_loss_pct:
                self.skipped_by_weekly_limit += 1
                return False, "weekly_limit"

        # Monthly loss limit.
        if capital > 0 and self.monthly_pnl < 0:
            monthly_loss_pct = -self.monthly_pnl / capital * 100.0
            if monthly_loss_pct >= self.config.max_monthly_loss_pct:
                self.skipped_by_monthly_limit += 1
                return False, "monthly_limit"

        # Max simultaneous positions.
        open_positions = sum(
            1 for d in self.strategy.datas if self.strategy.getposition(d).size != 0
        )
        if open_positions >= self.config.max_positions:
            self.skipped_by_max_positions += 1
            return False, "max_positions"

        # Consecutive losses.
        if self.consecutive_losses >= 3:
            self.skipped_by_consecutive_losses += 1
            return False, "consecutive_losses"

        # ATR gate: reject stops that are too wide relative to ATR.
        if self.config.check_atr:
            entry_price = float(self.strategy.data.close[0])
            atr = self._get_atr()
            if atr <= 0:
                return False, "atr_not_ready"
            try:
                stop_price = self.calculate_stop_price(entry_price, direction)
                distance = abs(entry_price - stop_price)
                if distance > 0 and atr > 0:
                    ratio = distance / atr  # stop-to-ATR
                    if ratio > self.config.max_stop_to_atr_ratio:
                        self.skipped_by_atr += 1
                        return False, "stop_too_wide"
            except Exception as exc:
                logger.debug("ATR gate failed: %s", exc)

        # Position sizing must be > 0.
        entry_price = float(self.strategy.data.close[0])
        try:
            stop_price = self.calculate_stop_price(entry_price, direction)
            size = self.calculate_position_size(entry_price, stop_price)
            if size <= 0:
                self.skipped_by_size_zero += 1
                return False, "size_zero"
        except Exception as exc:
            logger.debug("Size check failed: %s", exc)

        return True, "ok"

    # ------------------------------------------------------------------
    #  Calculators (thin wrappers around pure functions)
    # ------------------------------------------------------------------

    def calculate_stop_price(self, price: float, direction: Direction) -> float:
        return _stop_price(self.strategy, self.config, price, direction)

    def calculate_take_profit_price(
        self, entry_price: float, stop_price: float, direction: Direction
    ) -> float:
        return _tp_price(entry_price, stop_price, direction, self.config.take_profit_rr)

    def calculate_position_size(self, entry_price: float, stop_price: float) -> int:
        capital = self._get_capital()
        multiplier = self._get_multiplier()
        return calculate_size(
            capital=capital,
            entry_price=entry_price,
            stop_price=stop_price,
            config=self.config,
            contract_multiplier=multiplier,
        )

    def stop_distance(self, entry_price: float, direction: Direction) -> float:
        return _stop_distance(self.strategy, self.config, entry_price, direction)

    # ------------------------------------------------------------------
    #  Internals
    # ------------------------------------------------------------------

    def _get_capital(self) -> float:
        return float(self.strategy.broker.getvalue())

    def _get_atr(self) -> float:
        """Return the latest ATR value, computing it lazily and caching.

        Returns 0.0 if the indicator has not warmed up yet.
        """
        if not hasattr(self.strategy, "_risk_atr"):
            self.strategy._risk_atr = bt.indicators.ATR(
                self.strategy.data, period=self.config.atr_period
            )
        try:
            value = self.strategy._risk_atr[0]
        except IndexError:
            return 0.0
        return float(value) if value == value else 0.0  # NaN guard

    def _get_multiplier(self) -> Decimal | None:
        """Load contract_multiplier from instrument_specs once.

        Returns None for stocks or unknown symbols.
        """
        if self._multiplier_loaded:
            return self._multiplier
        self._multiplier_loaded = True

        try:
            symbol = self.strategy.data._name
        except AttributeError:
            return None
        if not symbol:
            return None

        try:
            with SessionLocal() as db:
                spec = db.execute(
                    select(InstrumentSpec).where(InstrumentSpec.symbol == symbol)
                ).scalar_one_or_none()
            if spec is not None and spec.contract_multiplier is not None:
                self._multiplier = spec.contract_multiplier
        except Exception as exc:
            logger.debug("Could not load multiplier for %s: %s", symbol, exc)

        return self._multiplier

    # ------------------------------------------------------------------
    #  Reporting
    # ------------------------------------------------------------------

    def get_stats(self) -> dict:
        """Return a dict of risk metrics for BacktestResult."""

        def _avg(values: list[float]) -> float:
            return sum(values) / len(values) if values else 0.0

        return {
            "avg_risk_per_trade": _avg(self._risk_pcts),
            "avg_rr_realized": _avg(self._rr_realized),
            "avg_position_size_pct": _avg(self._sizes_pct),
            "stops_hit": self.stops_hit,
            "take_profits_hit": self.take_profits_hit,
            "max_consecutive_losses": self.max_consecutive_losses,
            "skipped_by_atr": self.skipped_by_atr,
            "skipped_by_daily_limit": self.skipped_by_daily_limit,
            "skipped_by_weekly_limit": self.skipped_by_weekly_limit,
            "skipped_by_monthly_limit": self.skipped_by_monthly_limit,
            "skipped_by_max_positions": self.skipped_by_max_positions,
            "skipped_by_consecutive_losses": self.skipped_by_consecutive_losses,
            "skipped_by_size_zero": self.skipped_by_size_zero,
            "skipped_by_direction": self.skipped_by_direction,
        }
