from datetime import datetime
from typing import Literal

from fastapi import APIRouter, Depends, Query
from sqlalchemy import func, select
from sqlalchemy.dialects.sqlite import insert as sqlite_insert
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.models.candle import Candle
from app.schemas.candle import CandleCreate, CandleListResponse, CandleRead

router = APIRouter(prefix="/candles", tags=["candles"])

MAX_LIMIT = 10_000
DEFAULT_LIMIT = 1_000


@router.post("", response_model=list[CandleRead], status_code=201)
def create_candles(
    candles: list[CandleCreate],
    db: Session = Depends(get_db),
) -> list[CandleRead]:
    """Upsert a batch of candles with ON CONFLICT DO NOTHING.

    Idempotent: re-running with the same batch skips existing rows.
    """
    if not candles:
        return []

    rows = [c.model_dump() for c in candles]

    stmt = sqlite_insert(Candle).values(rows)
    stmt = stmt.on_conflict_do_nothing(
        index_elements=["symbol", "timeframe", "timestamp"]
    )
    db.execute(stmt)
    db.commit()

    symbols = {c.symbol for c in candles}
    timeframes = {c.timeframe for c in candles}
    timestamps = [c.timestamp for c in candles]

    read_stmt = select(Candle).where(
        Candle.symbol.in_(symbols),
        Candle.timeframe.in_(timeframes),
        Candle.timestamp.in_(timestamps),
    )
    return list(db.execute(read_stmt).scalars().all())


@router.get("", response_model=CandleListResponse)
def list_candles(
    symbol: str = Query(..., min_length=1, max_length=20),
    timeframe: int = Query(..., ge=1),
    start: datetime | None = Query(None, alias="start"),
    end: datetime | None = Query(None, alias="end"),
    limit: int = Query(DEFAULT_LIMIT, ge=1, le=MAX_LIMIT),
    offset: int = Query(0, ge=0),
    order: Literal["asc", "desc"] = Query("asc"),
    db: Session = Depends(get_db),
) -> CandleListResponse:
    """Read candles by symbol, timeframe, period with pagination.

    - `total` in the response is the full count matching the filter,
      ignoring `limit`/`offset` — needed for pagination UI.
    - `order` sorts by timestamp: `asc` (oldest first, default) or
      `desc` (newest first).
    """
    # Base filter shared by count and data queries.
    filters = [
        Candle.symbol == symbol,
        Candle.timeframe == timeframe,
    ]
    if start is not None:
        filters.append(Candle.timestamp >= start)
    if end is not None:
        filters.append(Candle.timestamp <= end)

    # Total count (ignoring limit/offset) for pagination metadata.
    count_stmt = select(func.count(Candle.id)).where(*filters)
    total = db.execute(count_stmt).scalar_one()

    # Order direction.
    order_clause = (
        Candle.timestamp.asc() if order == "asc" else Candle.timestamp.desc()
    )

    # Data page.
    data_stmt = (
        select(Candle)
        .where(*filters)
        .order_by(order_clause)
        .limit(limit)
        .offset(offset)
    )
    items = list(db.execute(data_stmt).scalars().all())

    return CandleListResponse(
        items=[CandleRead.model_validate(c) for c in items],
        total=total,
        limit=limit,
        offset=offset,
    )