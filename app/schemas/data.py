from datetime import date, datetime
from typing import Literal

from pydantic import BaseModel, Field, model_validator


class LoadRequest(BaseModel):
    """Request body for POST /api/v1/data/load."""

    symbol: str = Field(..., min_length=2, max_length=20, pattern=r"^[A-Z][A-Z0-9]*$")
    timeframe: Literal[1, 5, 10, 30, 60, 120, 240, 24] = 24
    start: date
    end: date

    @model_validator(mode="after")
    def check_dates(self) -> "LoadRequest":
        if self.start > self.end:
            raise ValueError("start must be <= end")
        return self


class LoadReport(BaseModel):
    """Response of POST /api/v1/data/load."""

    symbol: str
    timeframe: int
    start: date
    end: date
    fetched: int
    inserted: int
    duplicates_skipped: int
    duration_seconds: float


class DataSummaryItem(BaseModel):
    """One (symbol, timeframe) summary."""

    model_config = {"from_attributes": True}

    symbol: str
    timeframe: int
    candles_count: int
    first_timestamp: datetime
    last_timestamp: datetime


class DataSummaryResponse(BaseModel):
    """Response of GET /api/v1/data/summary."""

    items: list[DataSummaryItem]
    total_symbols: int
    total_candles: int


class DeleteResponse(BaseModel):
    """Response of DELETE /api/v1/data/{symbol}/{timeframe}."""

    symbol: str
    timeframe: int
    deleted: int
