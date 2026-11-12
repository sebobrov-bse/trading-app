"""Gerchik debug endpoint: recompute levels on-the-fly for a given date.

GET /api/v1/gerchik/debug/{symbol}?date=YYYY-MM-DD

Does NOT write to the DB — purely for eyes-on verification.
"""

import logging
from datetime import date, datetime

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.strategies.gerchik.precompute import precompute_gerchik

logger = logging.getLogger(__name__)
router = APIRouter()


@router.get("/gerchik/debug/{symbol}")
def gerchik_debug(
    symbol: str,
    date_str: str | None = Query(default=None, alias="date"),
    db: Session = Depends(get_db),
) -> dict:
    """Recompute and return levels/trend/energy for one day."""
    if date_str is None:
        raise HTTPException(
            status_code=400,
            detail="Query parameter 'date' is required (YYYY-MM-DD)",
        )

    try:
        target = datetime.strptime(date_str, "%Y-%m-%d").date()
    except ValueError:
        raise HTTPException(
            status_code=400,
            detail=f"Invalid date '{date_str}', expected YYYY-MM-DD",
        )

    days = precompute_gerchik(db, symbol.upper(), target, target)
    if not days:
        raise HTTPException(
            status_code=404,
            detail=f"No precomputed day for {symbol} on {target}",
        )

    day = days[0]

    # Levels in the spec format.
    levels_out = [
        {
            "price": round(r.level_price, 4),
            "type": r.level_type.value,
            "total_score": r.total_score,
        }
        for r in day.rows
    ]
    strong_out = [x for x in levels_out if x["total_score"] >= 5]

    # Key points (only those in last `lookback` from the day).
    kp_out = [
        {
            "price": round(kp.price, 4),
            "kind": kp.kind,
            "direction": kp.direction,
            "date": kp.date.isoformat(),
        }
        for kp in day.key_points
    ]

    # Energy breakdown (from the first level's energy, if any).
    energy = day.rows[0].energy.value if day.rows else "neutral"
    energy_details = {
        "levels_with_distribution": sum(1 for r in day.rows if r.energy.value == "distribution"),
        "levels_with_compression": sum(1 for r in day.rows if r.energy.value == "compression"),
        "levels_with_accumulation": sum(1 for r in day.rows if r.energy.value == "accumulation"),
        "total_levels": len(day.rows),
    }

    return {
        "date": day.date.isoformat(),
        "symbol": day.symbol,
        "atr": round(day.atr, 4),
        "prev_close": round(day.prev_close, 4),
        "close": round(day.close, 4),
        "path_ratio": round(day.path_ratio, 4),
        "trend": day.trend,
        "key_points": kp_out,
        "levels": levels_out,
        "strong_levels": strong_out,
        "energy": energy,
        "energy_details": energy_details,
    }
