from pydantic import BaseModel, Field


class BacktestRequest(BaseModel):
    """Request body for POST /api/v1/backtest."""

    symbol: str = Field(..., min_length=1, max_length=20)
    timeframe: int = Field(24, ge=1)
    start: str | None = Field(None, description="YYYY-MM-DD")
    end: str | None = Field(None, description="YYYY-MM-DD")
    cash: float = Field(100_000.0, gt=0)
    commission: float = Field(0.001, ge=0, le=0.1)
    fast: int = Field(10, ge=2, le=200)
    slow: int = Field(30, ge=3, le=500)


class BacktestResponse(BaseModel):
    """Response body for POST /api/v1/backtest."""

    symbol: str
    timeframe: int
    start_value: float
    final_value: float
    total_return_pct: float
    max_drawdown_pct: float
    sharpe_ratio: float | None
    total_trades: int
    won_trades: int
    lost_trades: int
    win_rate_pct: float | None