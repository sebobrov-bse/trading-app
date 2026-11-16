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
from app.strategies.gerchik.breakout import detect_breakout_setup
from app.strategies.gerchik.m1_stop_timing import check_stop_order_trigger

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
            # Walk forward through the day; when a setup is detected,
            # skip the bars already covered by its walk-forward window
            # (otherwise we re-detect the same setup on every bar).
            i = config.breakout_strong_move_lookback
            while i < len(m5_bars):
                prefix = m5_bars.iloc[: i + 1]
                setup_try = detect_breakout_setup(
                    prefix,
                    row.level_price,
                    direction,
                    row.energy.value,
                    day.atr,
                    config,
                )
                if setup_try is None:
                    i += 1
                    continue

                # Jump past the walk-forward window. The next bar to check
                # is the one AFTER the window we just covered.
                i = j + 1 if triggered else (i + 1 + config.breakout_max_wait_bars)

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


@router.get("/gerchik/breakout-debug/{symbol}")
def breakout_debug(
    symbol: str,
    date_str: str | None = Query(default=None, alias="date"),
    db: Session = Depends(get_db),
) -> dict:
    """Debug: run breakout setup detection for a single day.

    IMPORTANT: this endpoint is STATELESS — it does NOT replicate
    GerchikBreakout's full state machine. Specifically:
      - No 30-min cooldown after cancel/trigger.
      - No "already in position" gate.
      - No session_end block on new setups.

    Result: events count is typically HIGHER than what the strategy
    actually processes. This is intentional — for eyes-on verification
    we want to see ALL potential setups at a level/date, not just the
    ones that strategy happened to enter.

    For exact replay, run the strategy backtest (check_gerchik_breakout.py).

    Returns:
      events: list of {detected_at, stop_order_price, outcome, ...}
      triggered_count / cancelled_count: quick aggregates.
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

    # --- Load M1 ---
    repo = CandleRepository()
    df_m1 = repo.get_dataframe(
        symbol=symbol,
        timeframe=1,
        start=target,
        end=target + timedelta(days=1),
    )
    if df_m1 is None or df_m1.empty:
        raise HTTPException(
            status_code=404,
            detail=f"No M1 data for {symbol} on {target}",
        )

    df_m1 = df_m1.copy()
    df_m1.columns = [c.lower() for c in df_m1.columns]
    if "timestamp" in df_m1.columns:
        df_m1 = df_m1.set_index("timestamp")

    # --- Resample to M5 (with open, for gap detection) ---
    df_m5 = (
        df_m1.resample("5min", label="left", closed="left")
        .agg({"open": "first", "high": "max", "low": "min", "close": "last"})
        .dropna(subset=["high", "low", "close"])
    )

    if len(df_m5) < 3:
        raise HTTPException(
            status_code=404,
            detail=f"Not enough M5 bars for {symbol} on {target}",
        )

    m5_bars = df_m5.reset_index().rename(columns={"index": "timestamp"})
    if "timestamp" not in m5_bars.columns:
        m5_bars = m5_bars.rename(columns={m5_bars.columns[0]: "timestamp"})

    # --- Precompute D1 ---
    load_start = target - timedelta(days=30)
    days = precompute_gerchik(db, symbol, load_start, target)
    if not days:
        raise HTTPException(
            status_code=404,
            detail=f"No precompute for {symbol} on {target}",
        )
    day = days[-1]

    config = GerchikConfig()
    allowed_energy = ("accumulation", "compression")

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

    # Direction (with NEUTRAL fallback)
    if day.trend == "UP":
        direction = "LONG"
    elif day.trend == "DOWN":
        direction = "SHORT"
    else:
        if abs(day.path_ratio) >= config.system_neutral_path_min:
            direction = "LONG" if day.path_ratio > 0 else "SHORT"
        else:
            direction = None

    events: list[dict] = []
    skipped_energy = 0
    skipped_direction = 0

    if direction is None:
        skipped_direction = len(strong)
    else:
        for row in strong:
            # Walk forward. When a setup is found at bar i, its walk-forward
            # window is [i+1, i+max_wait_bars]. Then jump i to the bar AFTER
            # the window — otherwise we re-detect the same setup each bar.
            i = config.breakout_strong_move_lookback
            while i < len(m5_bars):
                prefix = m5_bars.iloc[: i + 1]
                setup_try = detect_breakout_setup(
                    prefix,
                    row.level_price,
                    direction,
                    row.energy.value,
                    day.atr,
                    config,
                )
                if setup_try is None:
                    i += 1
                    continue

                detected_ts = m5_bars.iloc[i]["timestamp"]
                events.append(
                    {
                        "level": round(row.level_price, 4),
                        "level_type": row.level_type.value,
                        "level_score": row.total_score,
                        "energy": row.energy.value,
                        "direction": direction,
                        "detected_at": detected_ts.isoformat()
                        if hasattr(detected_ts, "isoformat")
                        else str(detected_ts),
                        "stop_order_price": round(setup_try.stop_order_price, 4),
                        "setup_reason": setup_try.setup_reason,
                        "strong_move_before": setup_try.strong_move_before,
                        "outcome": "cancelled_expired",  # default; overridden below
                    }
                )

                last_checked = i  # last bar index touched by walk-forward
                for j in range(i + 1, min(i + 1 + config.breakout_max_wait_bars, len(m5_bars))):
                    last_checked = j

                    bar_close = float(m5_bars.iloc[j]["close"])
                    distance = abs(bar_close - row.level_price)
                    threshold = config.breakout_cancel_distance * setup_try.calculated_stop_size
                    if distance > threshold:
                        events[-1]["outcome"] = "cancelled_moved_away"
                        events[-1]["cancel_distance"] = round(distance, 4)
                        break

                    ts = m5_bars.iloc[j]["timestamp"]
                    m1_start_ts = ts - timedelta(minutes=5)
                    m1_in = df_m1[(df_m1.index > m1_start_ts) & (df_m1.index <= ts)]
                    if m1_in.empty:
                        continue

                    m1_list = [
                        {
                            "open": float(r["open"]),
                            "high": float(r["high"]),
                            "low": float(r["low"]),
                            "close": float(r["close"]),
                        }
                        for _, r in m1_in.iterrows()
                    ]
                    trig, fill = check_stop_order_trigger(
                        setup_try,
                        m1_list,
                        mode=config.breakout_m1_mode,
                    )
                    if trig:
                        events[-1]["outcome"] = "triggered"
                        events[-1]["fill_price"] = round(fill, 4)
                        events[-1]["m1_bars"] = len(m1_list)
                        break

                # Jump past the walk-forward window.
                i = last_checked + 1

    triggered_count = sum(1 for e in events if e["outcome"] == "triggered")
    return {
        "date": target.isoformat(),
        "symbol": symbol,
        "trend": day.trend,
        "path_ratio": round(day.path_ratio, 4),
        "atr": round(day.atr, 4),
        "direction": direction,
        "m1_bars": len(df_m1),
        "m5_bars": len(m5_bars),
        "levels_in_range": len(strong),
        "skipped_by_direction": skipped_direction,
        "skipped_by_energy": skipped_energy,
        "events": events,
        "triggered_count": triggered_count,
        "cancelled_count": len(events) - triggered_count,
    }
