"""Fluent Python Builder for StrategyConfig.

Why a builder:
- IDE autocompletion (no YAML typos)
- Type checking on condition arguments
- Reusable pieces (e.g. shared risk config)

Both YAML and Builder produce the same StrategyConfig, so the
compiler does not care which one was used.
"""

from typing import Any

from app.risk.config import RiskConfig
from app.strategies.builder.config import (
    Condition,
    ConstantRef,
    DirectionSection,
    FilterRef,
    IndicatorRef,
    LogicBlock,
    PriceRef,
    StrategyConfig,
)


# ---------------------------------------------------------------------------
#  Short factories for common references
# ---------------------------------------------------------------------------


def _indicator(name: str, **params: Any) -> IndicatorRef:
    return IndicatorRef(indicator=name, params=params)


def SMA(period: int = 20) -> IndicatorRef:
    return _indicator("SMA", period=period)


def EMA(period: int = 20) -> IndicatorRef:
    return _indicator("EMA", period=period)


def WMA(period: int = 20) -> IndicatorRef:
    return _indicator("WMA", period=period)


def RSI(period: int = 14) -> IndicatorRef:
    return _indicator("RSI", period=period)


def MACD(fast: int = 12, slow: int = 26, signal: int = 9) -> IndicatorRef:
    return _indicator("MACD", fast=fast, slow=slow, signal=signal)


def BollingerBands(period: int = 20, devfactor: float = 2.0) -> IndicatorRef:
    return _indicator("BollingerBands", period=period, devfactor=devfactor)


def ATR(period: int = 14) -> IndicatorRef:
    return _indicator("ATR", period=period)


def VolumeSMA(period: int = 20) -> IndicatorRef:
    return _indicator("VolumeSMA", period=period)


class Price:
    """Namespace for price references: Price.close(), Price.open(), ..."""

    @staticmethod
    def close() -> PriceRef:
        return PriceRef(price="close")

    @staticmethod
    def open() -> PriceRef:
        return PriceRef(price="open")

    @staticmethod
    def high() -> PriceRef:
        return PriceRef(price="high")

    @staticmethod
    def low() -> PriceRef:
        return PriceRef(price="low")

    @staticmethod
    def typical() -> PriceRef:
        return PriceRef(price="typical")

    @staticmethod
    def prev_close() -> PriceRef:
        return PriceRef(price="prev_close")


# ---------------------------------------------------------------------------
#  Internal logic-block builder
# ---------------------------------------------------------------------------


class _LogicBuilder:
    """Collects conditions for one logic block (entry or exit).

    Knows which slot it belongs to ('entry' or 'exit') and writes the
    resulting LogicBlock into the parent on .end().
    """

    def __init__(
        self,
        parent: "StrategyBuilder",
        logic: str,
        slot: str,
    ) -> None:
        self._parent = parent
        self._logic = logic
        self._slot = slot
        self._conditions: list[Condition] = []

    def condition(
        self,
        left: IndicatorRef | PriceRef,
        operator: str,
        right: IndicatorRef | PriceRef | ConstantRef | float | int,
    ) -> "_LogicBuilder":
        """Add a condition. Numeric `right` is auto-wrapped as ConstantRef."""
        if isinstance(right, (int, float)):
            right_ref: IndicatorRef | PriceRef | ConstantRef = ConstantRef(constant=float(right))
        else:
            right_ref = right

        self._conditions.append(Condition(left=left, operator=operator, right=right_ref))
        return self

    def end(self) -> "StrategyBuilder":
        """Close the block and store it on the parent."""
        block = LogicBlock(logic=self._logic, conditions=list(self._conditions))
        if self._slot == "entry":
            self._parent._entry = block
        elif self._slot == "exit":
            self._parent._exit = block
        return self._parent


# ---------------------------------------------------------------------------
#  StrategyBuilder
# ---------------------------------------------------------------------------


class StrategyBuilder:
    """Fluent builder for StrategyConfig.

    Usage:
        config = (StrategyBuilder()
            .name("My Strategy")
            .entry_and()
                .condition(RSI(14), "<", 35)
                .condition(Price.close(), ">", SMA(100))
            .end()
            .exit_or()
                .condition(RSI(14), ">", 65)
            .end()
            .risk(stop_type="atr", atr_multiplier=1.5)
            .direction(long=True, short=False)
            .build())
    """

    def __init__(self) -> None:
        self._name = "Unnamed Strategy"
        self._description = ""
        self._entry: LogicBlock | None = None
        self._exit: LogicBlock | None = None
        self._filters: list[FilterRef] = []
        self._risk: RiskConfig = RiskConfig()
        self._direction = DirectionSection(long=True, short=False)
        self._intraday_only = True

    # ---- metadata ----

    def name(self, value: str) -> "StrategyBuilder":
        self._name = value
        return self

    def description(self, value: str) -> "StrategyBuilder":
        self._description = value
        return self

    # ---- entry / exit ----

    def entry_and(self) -> _LogicBuilder:
        return _LogicBuilder(self, "AND", "entry")

    def entry_or(self) -> _LogicBuilder:
        return _LogicBuilder(self, "OR", "entry")

    def exit_and(self) -> _LogicBuilder:
        return _LogicBuilder(self, "AND", "exit")

    def exit_or(self) -> _LogicBuilder:
        return _LogicBuilder(self, "OR", "exit")

    # ---- filters ----

    def filter_volume(self, sma_period: int = 20, multiplier: float = 1.5) -> "StrategyBuilder":
        self._filters.append(
            FilterRef(
                type="volume",
                params={"sma_period": sma_period, "multiplier": multiplier},
            )
        )
        return self

    def filter_atr(self, period: int = 14, min_value: float = 0.0) -> "StrategyBuilder":
        self._filters.append(
            FilterRef(
                type="atr",
                params={"period": period, "min_value": min_value},
            )
        )
        return self

    def filter_time(self, sessions: list[str] | None = None) -> "StrategyBuilder":
        self._filters.append(
            FilterRef(
                type="time",
                params={"sessions": sessions or ["morning", "afternoon"]},
            )
        )
        return self

    def filter_day_of_week(self, days: list[str] | None = None) -> "StrategyBuilder":
        self._filters.append(
            FilterRef(
                type="day_of_week",
                params={"days": days or ["Mon", "Tue", "Wed", "Thu", "Fri"]},
            )
        )
        return self

    # ---- risk & direction ----

    def risk(self, **kwargs: Any) -> "StrategyBuilder":
        """Override RiskConfig fields.

        Example: .risk(stop_type='atr', atr_multiplier=2.0)
        """
        current = self._risk.model_dump()
        current.update(kwargs)
        self._risk = RiskConfig.model_validate(current)
        return self

    def direction(self, long: bool = True, short: bool = False) -> "StrategyBuilder":
        self._direction = DirectionSection(long=long, short=short)
        return self

    def intraday_only(self, value: bool = True) -> "StrategyBuilder":
        self._intraday_only = value
        return self

    # ---- build ----

    def build(self) -> StrategyConfig:
        """Validate and return the final StrategyConfig."""
        if self._entry is None:
            raise ValueError("entry block is required (use .entry_and()/.entry_or())")
        if self._exit is None:
            raise ValueError("exit block is required (use .exit_and()/.exit_or())")

        return StrategyConfig(
            name=self._name,
            description=self._description,
            version=1,
            entry=self._entry,
            exit=self._exit,
            filters=self._filters,
            risk=self._risk,
            direction=self._direction,
            intraday_only=self._intraday_only,
        )
