"""False Breakout (ЛП) detector: three sub-patterns.

1. fb_1_bar:
   - Wick pierces level (high > level for upward breakout -> expect SHORT).
   - Tail >= fb_min_tail_ratio * range.
   - Close returns BELOW level (for SHORT; ABOVE for LONG).
   - Stop order placed AT THE MOMENT of wick pierce (method: LP 1-bar
     means "fast entry on return", so stop is live from pierce, not
     from close). In backtest we simulate: setup detected at bar N,
     trigger checked on M1 of bar N+1.

2. fb_2_bars:
   - Bar N:   wick pierces level, does NOT close back yet.
   - Bar N+1: closes back below/above level.
   - Optional N+2: doesn't update extreme.
   - Stop order placed AFTER close of N+1.

3. fb_complex (off by default, fb_allow_complex=False):
   - Bar N:   wick pierces.
   - Bars N+1..M-1: no close back, no new extreme.
   - Bar M:   closes back below/above level.
   - Stop after close of M.

Direction semantics:
- "SHORT": false upward breakout (high > level, close < level).
- "LONG":  false downward breakout (low < level, close > level).
"""

import logging
from typing import Literal

import pandas as pd
from pydantic import BaseModel

from app.strategies.gerchik.config import GerchikConfig

logger = logging.getLogger(__name__)

Direction = Literal["LONG", "SHORT"]
Pattern = Literal["fb_1_bar", "fb_2_bars", "fb_complex"]


class FalseBreakoutSetup(BaseModel):
    """Detected false breakout setup with pending Stop order spec."""

    level: float
    direction: Direction  # "SHORT" / "LONG"
    pattern: Pattern  # "fb_1_bar" | "fb_2_bars" | "fb_complex"
    stop_order_price: float  # level ± offset (opposite to breakout)
    detected_at_bar: int
    expires_at_bar: int
    setup_reason: str  # "distribution" | "failed_accumulation"
    level_score: int
    calculated_stop_size: float
    tail_size: float  # how deep the wick pierced
    breakout_bar_index: int  # index in m5_bars of the piercing bar


def _normalize_m5(m5_bars: pd.DataFrame) -> pd.DataFrame:
    df = m5_bars.copy()
    df.columns = [c.lower() for c in df.columns]
    if "timestamp" in df.columns:
        df = df.sort_values("timestamp").reset_index(drop=True)
    return df


def _compute_offset(level: float, config: GerchikConfig) -> float:
    return max(
        config.fb_stop_order_offset_ticks * config.tick_size,
        config.fb_stop_order_offset_pct * level,
    )


def _tail_size_short(bar: pd.Series, level: float) -> float:
    """For SHORT (false upward breakout): tail = high - level."""
    return max(0.0, float(bar["high"]) - level)


def _tail_size_long(bar: pd.Series, level: float) -> float:
    """For LONG (false downward breakout): tail = level - low."""
    return max(0.0, level - float(bar["low"]))


def _is_breakout_bar(
    bar: pd.Series,
    level: float,
    direction: Direction,
) -> bool:
    """Wick pierced level."""
    if direction == "SHORT":
        return float(bar["high"]) > level
    return float(bar["low"]) < level


def _is_close_back(
    bar: pd.Series,
    level: float,
    direction: Direction,
    depth: float,
) -> bool:
    """Close returned to the 'correct' side by at least `depth`."""
    if direction == "SHORT":
        return float(bar["close"]) < level - depth
    return float(bar["close"]) > level + depth


def _tail_ok(
    bar: pd.Series,
    level: float,
    direction: Direction,
    config: GerchikConfig,
) -> bool:
    """Tail >= max(1 tick, fb_min_tail_ratio * range)."""
    if direction == "SHORT":
        tail = _tail_size_short(bar, level)
    else:
        tail = _tail_size_long(bar, level)
    rng = float(bar["high"]) - float(bar["low"])
    min_tail = max(config.tick_size, config.fb_min_tail_ratio * rng)
    return tail >= min_tail


def _no_extreme_update(
    next_bar: pd.Series,
    breakout_bar: pd.Series,
    direction: Direction,
) -> bool:
    """Next bar did NOT update the breakout bar's extreme."""
    if direction == "SHORT":
        return float(next_bar["high"]) <= float(breakout_bar["high"])
    return float(next_bar["low"]) >= float(breakout_bar["low"])


# ---------------------------------------------------------------------------
#  Pattern detectors
# ---------------------------------------------------------------------------


def _detect_1_bar(
    df: pd.DataFrame,
    level: float,
    direction: Direction,
    config: GerchikConfig,
) -> FalseBreakoutSetup | None:
    """Single-bar pattern: last bar pierces + closes back."""
    if len(df) < 2:
        return None
    bar = df.iloc[-1]

    if not _is_breakout_bar(bar, level, direction):
        return None
    if not _is_close_back(bar, level, direction, config.fb_min_close_depth):
        return None
    if not _tail_ok(bar, level, direction, config):
        return None

    if direction == "SHORT":
        tail_size = _tail_size_short(bar, level)
    else:
        tail_size = _tail_size_long(bar, level)

    return FalseBreakoutSetup(
        level=level,
        direction=direction,
        pattern="fb_1_bar",
        stop_order_price=0.0,  # filled by caller
        detected_at_bar=len(df) - 1,
        expires_at_bar=len(df) - 1 + config.fb_max_wait_bars,
        setup_reason="",  # filled by caller
        level_score=0,
        calculated_stop_size=level * config.fb_calculated_stop_pct,
        tail_size=tail_size,
        breakout_bar_index=len(df) - 1,
    )


def _detect_2_bars(
    df: pd.DataFrame,
    level: float,
    direction: Direction,
    config: GerchikConfig,
) -> FalseBreakoutSetup | None:
    """Two-bar pattern: [-2] pierces, [-1] closes back.

    Optionally checks fb_require_next_bar_no_extreme is impossible here
    (no third bar yet); only checks the second bar doesn't exceed the
    first's extreme. Since [-1] closed back, it also must not exceed
    the first bar's high (SHORT) / low (LONG).
    """
    if len(df) < 3:
        return None
    bar_n = df.iloc[-2]  # piercing bar
    bar_n1 = df.iloc[-1]  # returns back

    if not _is_breakout_bar(bar_n, level, direction):
        return None
    if not _tail_ok(bar_n, level, direction, config):
        return None
    if not _is_close_back(bar_n1, level, direction, config.fb_min_close_depth):
        return None
    if config.fb_require_next_bar_no_extreme:
        if not _no_extreme_update(bar_n1, bar_n, direction):
            return None

    if direction == "SHORT":
        tail_size = _tail_size_short(bar_n, level)
    else:
        tail_size = _tail_size_long(bar_n, level)

    return FalseBreakoutSetup(
        level=level,
        direction=direction,
        pattern="fb_2_bars",
        stop_order_price=0.0,
        detected_at_bar=len(df) - 1,
        expires_at_bar=len(df) - 1 + config.fb_max_wait_bars,
        setup_reason="",
        level_score=0,
        calculated_stop_size=level * config.fb_calculated_stop_pct,
        tail_size=tail_size,
        breakout_bar_index=len(df) - 2,
    )


def _detect_complex(
    df: pd.DataFrame,
    level: float,
    direction: Direction,
    config: GerchikConfig,
) -> FalseBreakoutSetup | None:
    """3+ bar pattern: pierce, hold, return.

    Walk back from the last bar (which closes back), find the piercing
    bar in the last N bars. All intermediate bars must not close back
    (otherwise it would be a 1- or 2-bar pattern) and must not update
    the piercing extreme.
    """
    if len(df) < 4:
        return None
    bar_last = df.iloc[-1]
    if not _is_close_back(bar_last, level, direction, config.fb_min_close_depth):
        return None

    # Walk back to find piercing bar.
    max_lookback = min(len(df) - 1, config.fb_max_wait_bars)
    pierce_idx = None
    for k in range(2, max_lookback + 1):
        idx = len(df) - 1 - k
        if idx < 0:
            break
        bar = df.iloc[idx]
        if not _is_breakout_bar(bar, level, direction):
            continue
        if not _tail_ok(bar, level, direction, config):
            continue
        # Bars between pierce_idx and last must NOT close back.
        ok = True
        for j in range(idx + 1, len(df) - 1):
            mid = df.iloc[j]
            if _is_close_back(mid, level, direction, config.fb_min_close_depth):
                ok = False
                break
            if not _no_extreme_update(mid, bar, direction):
                ok = False
                break
        if ok:
            pierce_idx = idx
            break

    if pierce_idx is None:
        return None

    pierce_bar = df.iloc[pierce_idx]
    if direction == "SHORT":
        tail_size = _tail_size_short(pierce_bar, level)
    else:
        tail_size = _tail_size_long(pierce_bar, level)

    return FalseBreakoutSetup(
        level=level,
        direction=direction,
        pattern="fb_complex",
        stop_order_price=0.0,
        detected_at_bar=len(df) - 1,
        expires_at_bar=len(df) - 1 + config.fb_max_wait_bars,
        setup_reason="",
        level_score=0,
        calculated_stop_size=level * config.fb_calculated_stop_pct,
        tail_size=tail_size,
        breakout_bar_index=pierce_idx,
    )


# ---------------------------------------------------------------------------
#  Public API
# ---------------------------------------------------------------------------


def detect_false_breakout(
    m5_bars: pd.DataFrame,
    level: float,
    direction: Direction,
    energy: str,
    level_score: int,
    config: GerchikConfig,
) -> FalseBreakoutSetup | None:
    """Try detect a false breakout at `level` in trade direction `direction`.

    Direction is the TRADE direction (opposite to the breakout):
      - direction="SHORT" -> false UP breakout (high > level, close < level).
      - direction="LONG"  -> false DOWN breakout (low < level, close > level).

    Energy:
      - DISTRIBUTION -> allowed.
      - ACCUMULATION / COMPRESSION -> allowed only if fb_allow_after_failed_accumulation.
      - NEUTRAL -> not allowed.

    Returns the first detected pattern (1 bar -> 2 bars -> complex).
    """
    if m5_bars is None or len(m5_bars) < 2:
        return None

    df = _normalize_m5(m5_bars)

    # --- Energy gate ---
    energy_lower = energy.lower()
    if energy_lower == "distribution":
        setup_reason = "distribution"
    elif energy_lower in ("accumulation", "compression"):
        if not config.fb_allow_after_failed_accumulation:
            return None
        setup_reason = "failed_accumulation"
    else:  # neutral
        return None

    # --- Try patterns in order ---
    setup = _detect_1_bar(df, level, direction, config)
    if setup is None:
        setup = _detect_2_bars(df, level, direction, config)
    if setup is None and config.fb_allow_complex:
        setup = _detect_complex(df, level, direction, config)

    if setup is None:
        return None

    # --- Fill stop order price (opposite to breakout) ---
    offset = _compute_offset(level, config)
    if direction == "SHORT":
        # False upward breakout -> SHORT; stop goes BELOW level (entry when
        # price returns down past level - offset).
        setup.stop_order_price = level - offset
    else:
        setup.stop_order_price = level + offset

    setup.setup_reason = setup_reason
    setup.level_score = level_score

    return setup
