from datetime import datetime
from decimal import Decimal

from pydantic import BaseModel, ConfigDict, Field


class CandleBase(BaseModel):
    """Shared fields for candle schemas."""

    symbol: str = Field(..., min_length=1, max_length=20)
    timeframe: int = Field(..., ge=1)
    timestamp: datetime
    open: Decimal
    high: Decimal
    low: Decimal
    close: Decimal
    volume: int = Field(..., ge=0)
    value: Decimal | None = None


class CandleCreate(CandleBase):
    """Schema for creating a candle (POST body)."""


class CandleRead(CandleBase):
    """Schema for reading a candle from DB (API response)."""

    model_config = ConfigDict(from_attributes=True)

    id: int
    created_at: datetime