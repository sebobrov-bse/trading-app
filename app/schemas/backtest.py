from datetime import date
from typing import Any, Literal

from pydantic import BaseModel, Field, model_validator


class BacktestRequest(BaseModel):
    """Request body for POST /api/v1/backtest/run."""

    symbol: str = Field(
        ..., min_length=2, max_length=20, pattern=r"^[A-Z][A-Z0-9]*$"
    )
    timeframe: Literal[1, 10, 60, 24] = 24
    start: date
    end: date
    strategy: str = Field(..., min_length=1, max_length=50)
    params: dict[str, Any] = Field(default_factory=dict)
    cash: float = Field(100_000.0, gt=0)
    commission: float = Field(0.001, ge=0, le=0.1)

    @model_validator(mode="after")
    def check_dates(self) -> "BacktestRequest":
        if self.start > self.end:
            raise ValueError("start must be <= end")
        return self


class BacktestResult(BaseModel):
    """Response body for POST /api/v1/backtest/run."""

    symbol: str
    timeframe: int
    start: date
    end: date
    strategy: str
    params: dict[str, Any]
    bars: int
    trades: int
    final_value: float
    pnl: float
    pnl_percent: float
    win_rate: float
    max_drawdown: float