from datetime import datetime

from pydantic import BaseModel, Field


class Candle(BaseModel):
    """OHLCV candle from a market data provider.

    Transport model — what a provider returns. NOT the SQLAlchemy model.
    Mapping to DB happens in the storage layer.
    """

    ticker: str = Field(..., min_length=1, max_length=20)
    timeframe: int = Field(..., ge=1)
    begin: datetime
    end: datetime
    open: float
    close: float
    high: float
    low: float
    value: float = Field(..., ge=0)
    volume: int = Field(..., ge=0)