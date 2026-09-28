from datetime import datetime

from fastapi import APIRouter, Depends, Query
from sqlalchemy import select
from sqlalchemy.dialects.sqlite import insert as sqlite_insert
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.models.candle import Candle
from app.schemas.candle import CandleCreate, CandleRead

router = APIRouter(prefix="/candles", tags=["candles"])

# Hard limit on response size. Prevents pulling tens of thousands of rows.
MAX_LIMIT = 10_000
DEFAULT_LIMIT = 1_000


@router.post("", response_model=list[CandleRead], status_code=201)
def create_candles(
    candles: list[CandleCreate],
    db: Session = Depends(get_db),
) -> list[CandleRead]:
    """Upsert a batch of candles.

    Uses SQLite ON CONFLICT DO NOTHING on (symbol, timeframe, timestamp).
    Re-running with the same batch is safe: existing rows are skipped.
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

    # Read back by (symbol, timeframe, timestamp) to return DB-populated fields.
    symbols = {c.symbol for c in candles}
    timeframes = {c.timeframe for c in candles}
    timestamps = [c.timestamp for c in candles]

    read_stmt = select(Candle).where(
        Candle.symbol.in_(symbols),
        Candle.timeframe.in_(timeframes),
        Candle.timestamp.in_(timestamps),
    )
    result = db.execute(read_stmt).scalars().all()
    return list(result)


@router.get("", response_model=list[CandleRead])
def list_candles(
    symbol: str = Query(..., min_length=1, max_length=20),
    timeframe: int = Query(..., ge=1),
    from_ts: datetime | None = Query(None, alias="from"),
    till_ts: datetime | None = Query(None, alias="till"),
    limit: int = Query(DEFAULT_LIMIT, ge=1, le=MAX_LIMIT),
    db: Session = Depends(get_db),
) -> list[CandleRead]:
    """Read candles by symbol, timeframe, and optional date range.

    Ordered by timestamp ascending. Hard limit on response size.
    """
    stmt = select(Candle).where(
        Candle.symbol == symbol,
        Candle.timeframe == timeframe,
    )

    if from_ts is not None:
        stmt = stmt.where(Candle.timestamp >= from_ts)
    if till_ts is not None:
        stmt = stmt.where(Candle.timestamp <= till_ts)

    stmt = stmt.order_by(Candle.timestamp.asc()).limit(limit)

    return list(db.execute(stmt).scalars().all())