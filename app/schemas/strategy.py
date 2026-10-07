"""Pydantic schemas for strategy metadata.

Unified format for all strategies: Python classes, builtin YAML,
custom from DB. Frontend uses this to build forms dynamically.
"""

from typing import Literal

from pydantic import BaseModel, Field


class StrategyParamSpec(BaseModel):
    """One parameter of a strategy (for dynamic form rendering)."""

    name: str = Field(..., min_length=1, max_length=50)
    type: Literal["int", "float", "bool", "str"] = "int"
    default: int | float | bool | str = 0
    min: int | float | None = None
    max: int | float | None = None
    description: str = ""


class RiskConfigPreview(BaseModel):
    """Compact RiskConfig for UI (5-6 key fields)."""

    use_risk_management: bool = True
    stop_type: Literal["atr", "percent", "n_bars"] = "atr"
    atr_multiplier: float = 1.5
    take_profit_rr: float = 3.0
    risk_per_trade_pct: float = 0.5


class DirectionSpec(BaseModel):
    """Which directions are allowed."""

    long: bool = True
    short: bool = False


class StrategyMetadata(BaseModel):
    """Full metadata for one strategy."""

    name: str
    display_name: str
    description: str = ""
    source: Literal["python", "builtin", "custom"] = "python"
    is_custom: bool = False
    custom_id: int | None = None

    params: list[StrategyParamSpec] = Field(default_factory=list)
    default_risk_config: RiskConfigPreview = Field(default_factory=RiskConfigPreview)
    direction: DirectionSpec = Field(default_factory=DirectionSpec)
    tags: list[str] = Field(default_factory=list)
    intraday_only: bool = False


class StrategyListResponse(BaseModel):
    """Response for GET /api/v1/strategies."""

    items: list[StrategyMetadata]
    total: int
