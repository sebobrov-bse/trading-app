"""Detector for the Gerchik 'rejection' pattern (БСУ/БПУ1/БПУ2).

БСУ (Bar Подтверждения Уровня) is the confirmed 'level touched and
held' pattern. Composed of two consecutive M5 bars:

- БПУ1: bar that touched the level (wick reached level, close on
        the right side — below for SHORT, above for LONG).
- БПУ2: strictly next bar (bpu1_index + 1) that held the same
        plane — did not break the level, did not drift far from
        БПУ1's high/low.

If both conditions pass -> pattern found. Entry/stop/tp are then
derived from the level (not from ATR):

    stop_size = level * stop_loss_pct      (default 0.2% of level)
    luff      = stop_size * luff_ratio     (default 20% of stop)
    entry     = level ± luff
    stop      = entry ∓ stop_size
    tp        = entry ± min_rr * stop_size (± commission if enabled)

If `next_level` is too close (< room_to_move_multiplier * stop_size),
tp_price is set to None and rejection_reason='insufficient_room'.
"""

import logging
from typing import Literal

import pandas as pd
from pydantic import BaseModel

from app.strategies.gerchik.config import GerchikConfig
from app.strategies.gerchik.room_to_move import find_next_level

logger = logging.getLogger(__name__)

Direction = Literal["LONG", "SHORT"]


class RejectionPattern(BaseModel):
    """Detected БСУ pattern with full entry/stop/tp context."""

    bpu1_index: int
    bpu2_index: int
    bpu1_datetime: str | None = None
    bpu2_datetime: str | None = None
    level: float
    direction: Direction
    entry_price: float
    stop_price: float
    stop_size: float
    luff: float
    tp_price: float | None
    next_level: float | None
    room_to_move: float | None
    rejection_reason: str | None = None


# ---------------------------------------------------------------------------
#  Internal helpers
# ---------------------------------------------------------------------------


def _normalize_m5(m5_bars: pd.DataFrame) -> pd.DataFrame:
    """Lowercase columns; sort by timestamp if present; reset index."""
    df = m5_bars.copy()
    df.columns = [c.lower() for c in df.columns]
    if "timestamp" in df.columns:
        df = df.sort_values("timestamp").reset_index(drop=True)
    elif "datetime" in df.columns:
        df = df.sort_values("datetime").reset_index(drop=True)
    return df


def _compute_tolerance(level: float, config: GerchikConfig) -> float:
    """Tolerance for БПУ1 contact = max(ticks*tick_size, pct*level)."""
    return max(
        config.tolerance_bpu1_ticks * config.tick_size,
        config.tolerance_bpu1_pct * level,
    )


def _get_datetime(df: pd.DataFrame, idx: int) -> str | None:
    """Extract ISO datetime string from row if column exists."""
    for col in ("timestamp", "datetime"):
        if col in df.columns:
            val = df[col].iloc[idx]
            if hasattr(val, "isoformat"):
                return val.isoformat()
            return str(val)
    return None


def _is_bpu1(
    bar: pd.Series,
    level: float,
    direction: Direction,
    tolerance: float,
) -> bool:
    """BPU1: wick reaches level, close on the 'right' side."""
    high = float(bar["high"])
    low = float(bar["low"])
    close = float(bar["close"])
    if direction == "SHORT":
        # Wick touches level from below OR pokes above (within tolerance);
        # close is BELOW level (rejected downward).
        return abs(high - level) <= tolerance and close < level
    # LONG: wick touches level, close ABOVE level (rejected upward).
    return abs(low - level) <= tolerance and close > level


def _is_bpu2(
    bar: pd.Series,
    bpu1_bar: pd.Series,
    level: float,
    luff: float,
    direction: Direction,
    plane_tolerance: float,
) -> bool:
    """BPU2: level held, bar stays on the same plane as BPU1."""
    high = float(bar["high"])
    low = float(bar["low"])
    bpu1_high = float(bpu1_bar["high"])
    bpu1_low = float(bpu1_bar["low"])

    # Use a tiny float epsilon to avoid rejecting 'exactly touched' cases.
    eps = 1e-9

    if direction == "SHORT":
        # high <= level (no break above)
        # high >= level - luff (not far below — held the plane)
        # high <= bpu1_high * (1 + plane_tol) (not above BPU1's high)
        return (
            high <= level + eps
            and high >= level - luff
            and high <= bpu1_high * (1.0 + plane_tolerance)
        )
    # LONG mirror
    return (
        low >= level - eps
        and low <= level + luff
        and low >= bpu1_low * (1.0 - plane_tolerance)
    )


# ---------------------------------------------------------------------------
#  Public API
# ---------------------------------------------------------------------------


def find_rejection_pattern(
    m5_bars: pd.DataFrame,
    level: float,
    direction: Direction,
    all_levels: list[float],
    config: GerchikConfig,
) -> RejectionPattern | None:
    """Scan M5 bars for the LAST (closest to now) БСУ pattern.

    Iterates from the end backwards; returns the first valid
    (BPU1, BPU2) pair — so the returned pattern is the most recent
    one. If no valid pair -> None.

    m5_bars must contain at least 2 rows.
    """
    if m5_bars is None or len(m5_bars) < 2:
        return None

    df = _normalize_m5(m5_bars)
    tolerance = _compute_tolerance(level, config)
    stop_size = level * config.stop_loss_pct
    luff = stop_size * config.luff_ratio

    # Iterate backwards: the returned pattern is the freshest one.
    for i in range(len(df) - 2, -1, -1):
        bpu1_bar = df.iloc[i]
        bpu2_bar = df.iloc[i + 1]

        if not _is_bpu1(bpu1_bar, level, direction, tolerance):
            continue
        if not _is_bpu2(
            bpu2_bar,
            bpu1_bar,
            level,
            luff,
            direction,
            config.bpu2_plane_tolerance,
        ):
            continue

        # Entry / stop / tp.
        if direction == "SHORT":
            entry = level - luff
            stop_price = entry + stop_size
        else:  # LONG
            entry = level + luff
            stop_price = entry - stop_size

        # Room to move: nearest level in trade direction.
        next_level = find_next_level(
            level,
            direction.lower(),
            all_levels,
        )
        if next_level is None:
            room_to_move: float | None = None
            room_ok = True
        else:
            room_to_move = abs(next_level - entry)
            room_ok = room_to_move >= (config.room_to_move_multiplier * stop_size)

        # Take profit.
        tp_distance = config.min_rr * stop_size
        commission = (
            entry * config.commission_rate * 2.0
            if config.include_commission_in_tp
            else 0.0
        )

        if not room_ok:
            tp_price: float | None = None
            reason: str | None = "insufficient_room"
        else:
            if direction == "SHORT":
                tp_price = entry - tp_distance - commission
            else:  # LONG
                tp_price = entry + tp_distance + commission
            reason = None

        return RejectionPattern(
            bpu1_index=i,
            bpu2_index=i + 1,
            bpu1_datetime=_get_datetime(df, i),
            bpu2_datetime=_get_datetime(df, i + 1),
            level=level,
            direction=direction,
            entry_price=entry,
            stop_price=stop_price,
            stop_size=stop_size,
            luff=luff,
            tp_price=tp_price,
            next_level=next_level,
            room_to_move=room_to_move,
            rejection_reason=reason,
        )

    return None
