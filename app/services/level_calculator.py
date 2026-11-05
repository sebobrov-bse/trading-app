"""Pre-compute daily levels for a whole period.

Reads 1m candles from the DB, groups by date, computes VA/Pivot for
each day. Returns a dict {date: DailyLevels} for O(1) access inside
the strategy's next().
"""

import logging
from datetime import date, datetime

import pandas as pd
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.candle import Candle
from app.strategies.levin.levels import DailyLevels, calculate_daily_levels

logger = logging.getLogger(__name__)


def precompute_levels(
    session: Session,
    symbol: str,
    timeframe: int = 1,
    start: date | None = None,
    end: date | None = None,
    n_bins: int = 100,
    va_percent: float = 0.70,
) -> dict[date, DailyLevels]:
    """Load 1m candles, group by day, compute levels."""
    stmt = select(Candle).where(
        Candle.symbol == symbol,
        Candle.asset_type == "stock",
        Candle.timeframe == timeframe,
    )
    if start is not None:
        stmt = stmt.where(Candle.timestamp >= datetime.combine(start, datetime.min.time()))
    if end is not None:
        stmt = stmt.where(Candle.timestamp <= datetime.combine(end, datetime.max.time()))

    stmt = stmt.order_by(Candle.timestamp.asc())
    rows = session.execute(stmt).scalars().all()

    if not rows:
        logger.warning("No 1m candles for %s in period", symbol)
        return {}

    df = pd.DataFrame(
        {
            "timestamp": [r.timestamp for r in rows],
            "high": [float(r.high) for r in rows],
            "low": [float(r.low) for r in rows],
            "close": [float(r.close) for r in rows],
            "volume": [int(r.volume) for r in rows],
        }
    )
    df["date"] = df["timestamp"].dt.date

    result: dict[date, DailyLevels] = {}
    for day, group in df.groupby("date"):
        levels = calculate_daily_levels(group, n_bins=n_bins, va_percent=va_percent)
        if levels is not None:
            result[day] = levels

    logger.info(
        "Precomputed levels for %s: %s days",
        symbol,
        len(result),
    )
    return result
