"""Gerchik debug endpoint: recompute levels on-the-fly for a given date.

GET /api/v1/gerchik/debug/{symbol}?date=YYYY-MM-DD

Does NOT write to the DB — purely for eyes-on verification.
"""

import logging
from datetime import date, datetime, timedelta

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

import pandas as pd

from app.db.session import get_db
from app.services.candle_repository import CandleRepository
from app.strategies.gerchik.config import GerchikConfig
from app.strategies.gerchik.precompute import precompute_gerchik
from app.strategies.gerchik.rejection import find_rejection_pattern

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


@router.get("/gerchik/rejection-debug/{symbol}")
def rejection_debug(
    symbol: str,
    date_str: str | None = Query(default=None, alias="date"),
    db: Session = Depends(get_db),
) -> dict:
    """Debug: run rejection pattern detection for a single day.

    Loads M1 for the day, resamples to M5 via pandas, precomputes D1
    context (warmup 30 days), filters levels by energy + ±2*ATR from
    prev_close, and tries find_rejection_pattern on each level.

    Returns:
      - candidates: levels with a valid (tp_price != None) pattern.
      - no_pattern: levels in range where no pattern was detected.

    Does NOT trade, does NOT write to DB.
    """
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

    symbol = symbol.upper()

    # --- 1. Load M1 for the target day ---
    repo = CandleRepository()
    df_m1 = repo.get_dataframe(
        symbol=symbol,
        timeframe=1,
        start=target,
        end=target + timedelta(days=1),  # get_dataframe excludes `end`
    )
    if df_m1 is None or df_m1.empty:
        raise HTTPException(
            status_code=404,
            detail=f"No M1 data for {symbol} on {target}",
        )

    # --- 2. Resample M1 -> M5 (left-closed, left-labeled) ---
    df_m1 = df_m1.copy()
    df_m1.columns = [c.lower() for c in df_m1.columns]
    if "timestamp" in df_m1.columns:
        df_m1 = df_m1.set_index("timestamp")

    df_m5 = (
        df_m1.resample("5min", label="left", closed="left")
        .agg({"high": "max", "low": "min", "close": "last", "open": "first"})
        .dropna(subset=["high", "low", "close"])
    )

    if len(df_m5) < 2:
        raise HTTPException(
            status_code=404,
            detail=f"Not enough M5 bars for {symbol} on {target} (got {len(df_m5)})",
        )

    m5_bars = df_m5.reset_index().rename(columns={"index": "timestamp"})
    if "timestamp" not in m5_bars.columns:
        m5_bars = m5_bars.rename(columns={m5_bars.columns[0]: "timestamp"})

    # --- 3. Precompute D1 context (warmup 30 days) ---
    load_start = target - timedelta(days=30)
    days = precompute_gerchik(db, symbol, load_start, target)
    if not days:
        raise HTTPException(
            status_code=404,
            detail=f"No precompute for {symbol} on {target}",
        )
    day = days[-1]

    # --- 4. Filter levels: energy + ±2*ATR from prev_close ---
    config = GerchikConfig()
    allowed_energy = ("distribution", "neutral", "compression")

    if day.atr > 0 and day.prev_close > 0:
        day_low = day.prev_close - 2.0 * day.atr
        day_high = day.prev_close + 2.0 * day.atr
    else:
        day_low, day_high = 0.0, 1e9

    strong = [
        r
        for r in day.rows
        if r.energy.value in allowed_energy and day_low <= r.level_price <= day_high
    ]

    # --- 5. Direction (trend, NEUTRAL fallback by path_ratio) ---
    if day.trend == "UP":
        direction = "LONG"
    elif day.trend == "DOWN":
        direction = "SHORT"
    else:
        if abs(day.path_ratio) >= config.system_neutral_path_min:
            direction = "LONG" if day.path_ratio > 0 else "SHORT"
        else:
            direction = None

    # --- 6. Try find_rejection_pattern for each level ---
    all_levels = [r.level_price for r in strong]
    candidates: list[dict] = []
    no_pattern: list[dict] = []

    if direction is not None:
        for row in strong:
            pat = find_rejection_pattern(
                m5_bars,
                row.level_price,
                direction,
                all_levels,
                config,
            )
            if pat is None:
                no_pattern.append(
                    {
                        "level": round(row.level_price, 4),
                        "level_type": row.level_type.value,
                        "level_score": row.total_score,
                        "energy": row.energy.value,
                        "reason": "no_pattern",
                    }
                )
                continue

            room_ok = pat.rejection_reason is None

            # BPU1/BPU2 bars for eyes-on verification.
            def _bar_dict(idx: int) -> dict:
                b = m5_bars.iloc[idx]
                ts = b.get("timestamp")
                return {
                    "datetime": ts.isoformat() if hasattr(ts, "isoformat") else str(ts),
                    "high": round(float(b["high"]), 4),
                    "low": round(float(b["low"]), 4),
                    "close": round(float(b["close"]), 4),
                }

            candidates.append(
                {
                    "level": round(row.level_price, 4),
                    "level_type": row.level_type.value,
                    "level_score": row.total_score,
                    "energy": row.energy.value,
                    "direction": direction,
                    "bpu1": _bar_dict(pat.bpu1_index),
                    "bpu2": _bar_dict(pat.bpu2_index),
                    "entry_price": round(pat.entry_price, 4),
                    "stop_price": round(pat.stop_price, 4),
                    "stop_size": round(pat.stop_size, 4),
                    "luff": round(pat.luff, 4),
                    "tp_price": round(pat.tp_price, 4) if pat.tp_price is not None else None,
                    "next_level": round(pat.next_level, 4) if pat.next_level is not None else None,
                    "room_to_move": round(pat.room_to_move, 4)
                    if pat.room_to_move is not None
                    else None,
                    "room_ok": room_ok,
                    "rejection_reason": pat.rejection_reason,
                }
            )
    else:
        for row in strong:
            no_pattern.append(
                {
                    "level": round(row.level_price, 4),
                    "level_type": row.level_type.value,
                    "level_score": row.total_score,
                    "energy": row.energy.value,
                    "reason": "no_direction",
                }
            )

    return {
        "date": target.isoformat(),
        "symbol": symbol,
        "trend": day.trend,
        "path_ratio": round(day.path_ratio, 4),
        "atr": round(day.atr, 4),
        "prev_close": round(day.prev_close, 4),
        "close": round(day.close, 4),
        "direction": direction,
        "m1_bars": len(df_m1),
        "m5_bars": len(m5_bars),
        "levels_in_range": len(strong),
        "candidates": candidates,
        "no_pattern": no_pattern,
    }
