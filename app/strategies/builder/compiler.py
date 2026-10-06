"""Compile a StrategyConfig into a Backtrader Strategy class.

The compiler walks the config, builds Backtrader indicator lines
in __init__, and assembles entry/exit signals plus filters.

No code execution from user input: names are looked up in registries.
"""

import logging
from typing import Any

import backtrader as bt

from app.strategies.base import BaseStrategy
from app.strategies.builder.config import (
    Condition,
    ConstantRef,
    FilterRef,
    IndicatorRef,
    LogicBlock,
    PriceRef,
    StrategyConfig,
)
from app.strategies.builder.filters import FILTER_REGISTRY
from app.strategies.builder.indicators import INDICATOR_REGISTRY
from app.strategies.builder.logic import LOGIC_REGISTRY
from app.strategies.builder.operators import OPERATOR_REGISTRY

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
#  Reference builders: IndicatorRef / PriceRef / ConstantRef → line or float
# ---------------------------------------------------------------------------


def _build_ref(
    strategy: bt.Strategy,
    ref: IndicatorRef | PriceRef | ConstantRef,
) -> Any:
    """Turn a config reference into a Backtrader line or a Python float."""
    if isinstance(ref, ConstantRef):
        return float(ref.constant)

    if isinstance(ref, PriceRef):
        data = strategy.data
        mapping = {
            "close": lambda: data.close,
            "open": lambda: data.open,
            "high": lambda: data.high,
            "low": lambda: data.low,
            "typical": lambda: (data.high + data.low + data.close) / 3.0,
            "prev_close": lambda: bt.indicators.Lag(data.close, period=1),
        }
        return mapping[ref.price]()

    if isinstance(ref, IndicatorRef):
        spec = INDICATOR_REGISTRY[ref.indicator]
        if spec.factory is None:
            raise ValueError(f"Indicator {ref.indicator} has no factory")
        # VolumeSMA reads from volume, everything else from close.
        if ref.indicator == "VolumeSMA":
            source = strategy.data.volume
        else:
            source = strategy.data.close
        return spec.factory(source, ref.params)

    raise TypeError(f"Unknown reference type: {type(ref).__name__}")


# ---------------------------------------------------------------------------
#  Condition and logic compilers
# ---------------------------------------------------------------------------


def _build_condition(strategy: bt.Strategy, cond: Condition) -> Any:
    """Compile one condition: left OP right. Returns a line or bool."""
    left = _build_ref(strategy, cond.left)
    right = _build_ref(strategy, cond.right)
    op = OPERATOR_REGISTRY[cond.operator]
    return op(left, right)


def _build_logic_block(strategy: bt.Strategy, block: LogicBlock) -> Any:
    """Compile a LogicBlock (AND/OR over conditions)."""
    compiled = [_build_condition(strategy, c) for c in block.conditions]
    logic = LOGIC_REGISTRY[block.logic]
    return logic(compiled)


# ---------------------------------------------------------------------------
#  Filter compiler
# ---------------------------------------------------------------------------


def _build_filter(strategy: bt.Strategy, ref: FilterRef) -> Any:
    """Compile a filter into a boolean line."""
    t = ref.type
    p = ref.params

    if t == "volume":
        sma_period = int(p.get("sma_period", 20))
        mult = float(p.get("multiplier", 1.5))
        vol_sma = bt.indicators.SMA(strategy.data.volume, period=sma_period)
        return strategy.data.volume > vol_sma * mult

    if t == "atr":
        period = int(p.get("period", 14))
        min_value = float(p.get("min_value", 0.0))
        atr = bt.indicators.ATR(strategy.data, period=period)
        return atr > min_value

    if t == "time":
        sessions = p.get("sessions", ["morning", "afternoon"])
        # Simple implementation: use hour-of-day.
        # "morning"   : 07:00–12:00
        # "afternoon" : 12:00–18:00
        # "evening"   : 18:00–23:59
        # Backtrader doesn't expose hour as a line easily, so we
        # approximate with a custom indicator.
        return _SessionFilter(strategy.data, sessions=sessions)

    if t == "day_of_week":
        days = p.get("days", ["Mon", "Tue", "Wed", "Thu", "Fri"])
        return _DayOfWeekFilter(strategy.data, days=days)

    raise ValueError(f"Unknown filter type: {t}")


# ---------------------------------------------------------------------------
#  Custom filters (need to be bt.Indicator subclasses)
# ---------------------------------------------------------------------------


class _SessionFilter(bt.Indicator):
    """True when the current bar's hour falls into one of the sessions."""

    lines = ("session_ok",)
    params = (("sessions", ["morning", "afternoon"]),)

    _RANGES = {
        "morning": (7, 12),
        "afternoon": (12, 18),
        "evening": (18, 24),
    }

    def __init__(self) -> None:
        super().__init__()

    def next(self) -> None:
        hour = self.data.datetime.time(0).hour
        ok = False
        for s in self.p.sessions:
            lo, hi = self._RANGES.get(s, (0, 0))
            if lo <= hour < hi:
                ok = True
                break
        self.lines.session_ok[0] = 1.0 if ok else 0.0


class _DayOfWeekFilter(bt.Indicator):
    """True when the current bar's weekday is in the allowed list."""

    lines = ("day_ok",)
    params = (("days", ["Mon", "Tue", "Wed", "Thu", "Fri"]),)

    _WEEKDAYS = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]

    def __init__(self) -> None:
        super().__init__()

    def next(self) -> None:
        wd = self.data.datetime.date(0).weekday()
        name = self._WEEKDAYS[wd]
        self.lines.day_ok[0] = 1.0 if name in self.p.days else 0.0


# ---------------------------------------------------------------------------
#  The compiler itself
# ---------------------------------------------------------------------------


def compile_strategy(config: StrategyConfig) -> type[bt.Strategy]:
    """Return a Backtrader Strategy class compiled from the config.

    The returned class:
    - subclasses BaseStrategy (so it has safe_buy / safe_close / risk),
    - accepts a `risk_config` param (defaults to config.risk),
    - implements next() from entry/exit/filters.
    """

    def __init__(self: bt.Strategy) -> None:
        super(type(self), self).__init__()

        # ---- Build signals and filters as lazy lines ----
        self._entry_signal = _build_logic_block(self, config.entry)
        self._exit_signal = _build_logic_block(self, config.exit)
        self._filters = [_build_filter(self, f) for f in config.filters]

        # ---- Cache direction flags ----
        self._allow_long = config.direction.long
        self._allow_short = config.direction.short

    def next(self: bt.Strategy) -> None:
        # BaseStrategy._on_bar_start: bars counter, on_new_bar, dynamic levels.
        super(type(self), self).next()

        if self.order:
            return

        # Check filters first (they gate both entry and exit? No — only entry).
        filters_ok = True
        for f in self._filters:
            try:
                if not bool(f[0]):
                    filters_ok = False
                    break
            except (IndexError, TypeError):
                # Filter not warmed up yet — treat as "not OK".
                filters_ok = False
                break

        if not self.position:
            if filters_ok and bool(self._entry_signal[0]):
                direction = "long" if self._allow_long else "short"
                self.safe_buy(direction=direction)
        else:
            if bool(self._exit_signal[0]):
                self.safe_close()

    # ---- Build the class dynamically ----
    attrs = {
        "__init__": __init__,
        "next": next,
        # RiskConfig from the strategy config is the default; caller can
        # override via cerebro.addstrategy(cls, risk_config=other).
        "params": (("risk_config", config.risk),),
    }

    cls_name = f"Compiled_{config.name.replace(' ', '_')}"
    return type(cls_name, (BaseStrategy,), attrs)
