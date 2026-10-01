"""Data Manager endpoints: load, summary, delete."""

import logging

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from app.data_providers.moex_iss.client import MoexIssProvider
from app.db.session import get_db
from app.schemas.data import (
    DataSummaryItem,
    DataSummaryResponse,
    DeleteResponse,
    LoadReport,
    LoadRequest,
)
from app.services.candle_repository import CandleRepository
from app.services.data_loader import DataLoader

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/data", tags=["data"])


@router.post("/load", response_model=LoadReport)
async def load_data(request: LoadRequest) -> LoadReport:
    """Load historical candles from MOEX ISS into SQLite."""
    provider = MoexIssProvider()
    loader = DataLoader(provider)

    try:
        report = await loader.load_and_report(
            symbol=request.symbol,
            timeframe=request.timeframe,
            start=request.start,
            end=request.end,
        )
    except Exception as exc:
        logger.exception("Load failed for %s %s", request.symbol, request.timeframe)
        raise HTTPException(
            status_code=500,
            detail=f"Failed to load data: {type(exc).__name__}: {exc}",
        )

    return LoadReport(
        symbol=request.symbol,
        timeframe=request.timeframe,
        start=request.start,
        end=request.end,
        fetched=report.fetched,
        inserted=report.inserted,
        duplicates_skipped=report.duplicates_skipped,
        duration_seconds=report.duration_seconds,
    )


@router.get("/summary", response_model=DataSummaryResponse)
def get_summary(
    symbol: str | None = Query(None, min_length=2, max_length=20),
    timeframe: int | None = Query(None, ge=1),
) -> DataSummaryResponse:
    """Return aggregate stats per (symbol, timeframe)."""
    repo = CandleRepository()
    rows = repo.get_summary(symbol=symbol, timeframe=timeframe)

    items = [
        DataSummaryItem(
            symbol=r["symbol"],
            timeframe=r["timeframe"],
            candles_count=r["candles_count"],
            first_timestamp=r["first_timestamp"],
            last_timestamp=r["last_timestamp"],
        )
        for r in rows
    ]

    unique_symbols = len({i.symbol for i in items})
    total_candles = sum(i.candles_count for i in items)

    return DataSummaryResponse(
        items=items,
        total_symbols=unique_symbols,
        total_candles=total_candles,
    )


@router.delete("/{symbol}/{timeframe}", response_model=DeleteResponse)
def delete_data(symbol: str, timeframe: int) -> DeleteResponse:
    """Delete all candles for a (symbol, timeframe)."""
    repo = CandleRepository()
    deleted = repo.delete_candles(symbol.upper(), timeframe)

    if deleted == 0:
        raise HTTPException(
            status_code=404,
            detail=f"No candles found for {symbol} tf={timeframe}.",
        )

    return DeleteResponse(
        symbol=symbol.upper(),
        timeframe=timeframe,
        deleted=deleted,
    )
