from datetime import datetime
from decimal import Decimal

from pydantic import BaseModel, Field


class Candle(BaseModel):
    """OHLCV candle from a market data provider."""

    ticker: str = Field(..., min_length=1, max_length=20)
    asset_type: str = Field("stock", description="'stock' or 'future'")
    timeframe: int = Field(..., ge=1)
    begin: datetime
    end: datetime
    open: Decimal
    close: Decimal
    high: Decimal
    low: Decimal
    value: Decimal = Field(..., ge=0)
    volume: int = Field(..., ge=0)
