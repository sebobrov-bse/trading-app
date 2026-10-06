"""Pydantic models for strategy configuration (YAML/JSON).

All references (indicators, operators, filters) are validated against
registries. Invalid names raise ValidationError with a clear message.
"""

from typing import Any, Literal

from pydantic import BaseModel, Field, field_validator, model_validator

from app.risk.config import RiskConfig
from app.strategies.builder.filters import FILTER_REGISTRY
from app.strategies.builder.indicators import INDICATOR_REGISTRY
from app.strategies.builder.operators import OPERATOR_REGISTRY


class IndicatorRef(BaseModel):
    """Reference to an indicator with parameters."""

    indicator: str
    params: dict[str, Any] = Field(default_factory=dict)

    @field_validator("indicator")
    @classmethod
    def _check_indicator(cls, v: str) -> str:
        if v not in INDICATOR_REGISTRY:
            raise ValueError(f"Unknown indicator '{v}'. Available: {sorted(INDICATOR_REGISTRY)}")
        return v


class PriceRef(BaseModel):
    """Reference to a price series."""

    price: Literal["close", "open", "high", "low", "typical", "prev_close"]


class ConstantRef(BaseModel):
    """Reference to a constant value."""

    constant: float


LeftRef = IndicatorRef | PriceRef
RightRef = IndicatorRef | PriceRef | ConstantRef


class Condition(BaseModel):
    """One comparison: left OP right."""

    left: LeftRef
    operator: str
    right: RightRef

    @field_validator("operator")
    @classmethod
    def _check_operator(cls, v: str) -> str:
        if v not in OPERATOR_REGISTRY:
            raise ValueError(f"Unknown operator '{v}'. Available: {sorted(OPERATOR_REGISTRY)}")
        return v


class LogicBlock(BaseModel):
    """A group of conditions joined by AND / OR."""

    logic: Literal["AND", "OR"] = "AND"
    conditions: list[Condition] = Field(..., min_length=1)


class FilterRef(BaseModel):
    """Reference to a filter with parameters."""

    type: str
    params: dict[str, Any] = Field(default_factory=dict)

    @field_validator("type")
    @classmethod
    def _check_filter(cls, v: str) -> str:
        if v not in FILTER_REGISTRY:
            raise ValueError(f"Unknown filter '{v}'. Available: {sorted(FILTER_REGISTRY)}")
        return v


class DirectionSection(BaseModel):
    """Which directions are allowed."""

    long: bool = True
    short: bool = False

    @model_validator(mode="after")
    def _check_at_least_one(self) -> "DirectionSection":
        if not self.long and not self.short:
            raise ValueError("At least one of long/short must be True")
        return self


class StrategyConfig(BaseModel):
    """Full strategy configuration."""

    name: str = Field(..., min_length=1, max_length=100)
    description: str = ""
    version: int = Field(1, ge=1)

    entry: LogicBlock
    exit: LogicBlock
    filters: list[FilterRef] = Field(default_factory=list)

    risk: RiskConfig = Field(default_factory=RiskConfig)
    direction: DirectionSection = Field(default_factory=DirectionSection)
    intraday_only: bool = True
