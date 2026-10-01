from datetime import date, datetime
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator


class BacktestRequest(BaseModel):
    """Request body for POST /api/v1/backtest/run."""

    symbol: str = Field(..., min_length=2, max_length=20, pattern=r"^[A-Z][A-Z0-9]*$")
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


class TradeInfo(BaseModel):
    entry_time: datetime
    exit_time: datetime
    entry_price: float
    exit_price: float
    size: float
    bars_held: int
    pnl: float
    pnl_net: float
    pnl_percent: float


class EquityPoint(BaseModel):
    timestamp: datetime
    value: float


class BacktestResult(BaseModel):
    id: int | None = None
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
    cagr: float
    max_drawdown: float
    sharpe: float
    sortino: float
    calmar: float
    win_rate: float
    profit_factor: float
    avg_win: float
    avg_loss: float
    exposure: float
    equity_curve: list[EquityPoint]
    trades_list: list[TradeInfo]


class BacktestHistoryItem(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    symbol: str
    timeframe: int
    strategy: str
    pnl: float
    pnl_percent: float
    sharpe: float
    max_drawdown: float
    trades_count: int
    created_at: datetime


class BacktestHistoryResponse(BaseModel):
    items: list[BacktestHistoryItem]
    total: int
    limit: int
    offset: int


class BacktestDetails(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    symbol: str
    timeframe: int
    start_date: datetime
    end_date: datetime
    strategy: str
    params: dict[str, Any]
    cash: float
    commission: float
    bars: int
    trades_count: int
    final_value: float
    pnl: float
    pnl_percent: float
    cagr: float
    sharpe: float
    sortino: float
    calmar: float
    max_drawdown: float
    win_rate: float
    profit_factor: float
    avg_win: float
    avg_loss: float
    exposure: float
    created_at: datetime
    trades_list: list[TradeInfo] = []
    equity_curve: list[EquityPoint] = []


class TopStrategyItem(BaseModel):
    """One strategy in the top-N aggregate."""

    strategy: str
    count: int
    avg_sharpe: float
    avg_pnl: float
    avg_max_drawdown: float
