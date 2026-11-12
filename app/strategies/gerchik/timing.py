"""M1 timing: find the exact entry moment on 1-minute bars.

For a given (day, level, direction, pattern), scans M1 bars in order:

1. Find first touch of the level.
2. Wait up to m1_max_wait_bars for pattern confirmation.
3. Return EntryDecision — either enter_long/enter_short with entry &
   stop, or skip with reason.

The actual pattern detection lives in patterns/*.py; this module is a
thin dispatcher plus M1 ATR calculation.
"""

import logging
from dataclasses import dataclass
from typing import Literal

import numpy as np
import pandas as pd

from app.strategies.gerchik.config import GerchikConfig

logger = logging.getLogger(__name__)

Direction = Literal["long", "short"]
PatternKind = Literal["bounce", "breakout", "limit_player"]
Action = Literal["enter_long", "enter_short", "skip"]


@dataclass(frozen=True)
class EntryDecision:
    """Result of M1 timing for one (level, day)."""

    action: Action
    entry_price: float | None
    stop_price: float | None
    reason: str
    bars_waited: int
    touch_idx: int | None  # index in bars_m1 where touch happened
    entry_idx: int | None  # index where entry decision was made


def calculate_m1_atr(
    bars_m1: pd.DataFrame,
    config: GerchikConfig,
) -> float:
    """M1 ATR as median of last N ranges.

    Why median (not the two-step filter of D1): on M1 there are many
    'quiet' bars (range ≈ 0), and any mean-based measure would be
    dragged down. Median of ranges is the typical minute's range,
    which is what we need for 'bounce > 0.5 ATR' thresholds.

    Accepts both lowercase and uppercase column names (High/Low/…)
    — defensive normalization, since callers may pass raw DB rows
    without going through `_normalize_bars`.
    """
    if len(bars_m1) == 0:
        return 0.0
    df = bars_m1.copy()
    df.columns = [c.lower() for c in df.columns]
    tail = df.tail(config.m1_atr_period)
    ranges = (tail["high"] - tail["low"]).to_numpy(dtype=float)
    if len(ranges) == 0:
        return 0.0
    return float(np.median(ranges))


def _normalize_bars(bars_m1: pd.DataFrame) -> pd.DataFrame:
    """Lowercase columns, sort by timestamp."""
    df = bars_m1.copy()
    df.columns = [c.lower() for c in df.columns]
    if "timestamp" in df.columns:
        df = df.sort_values("timestamp").reset_index(drop=True)
    return df


def find_entry_signal(
    bars_m1: pd.DataFrame,
    level_price: float,
    direction: Direction,
    pattern: PatternKind,
    config: GerchikConfig,
) -> EntryDecision:
    """Dispatch to the requested pattern detector.

    Returns EntryDecision.skip with reason='unsupported_pattern' if
    the pattern is not implemented yet (S.2b.1 placeholder).
    """
    if bars_m1 is None or len(bars_m1) == 0:
        return _skip("empty_bars")

    df = _normalize_bars(bars_m1)
    atr_m1 = calculate_m1_atr(df, config)
    if atr_m1 <= 0:
        return _skip("atr_zero")

    # Placeholders — real logic in S.2b.2-4.
    if pattern == "bounce":
        from app.strategies.gerchik.patterns import bounce

        return bounce.bounce_entry(df, level_price, direction, atr_m1, config)

    if pattern == "breakout":
        from app.strategies.gerchik.patterns import breakout

        return breakout.breakout_entry(df, level_price, direction, atr_m1, config)

    if pattern == "limit_player":
        from app.strategies.gerchik.patterns import limit_player

        return limit_player.limit_player_entry(
            df,
            level_price,
            direction,
            atr_m1,
            config,
        )

    return _skip(f"unsupported_pattern:{pattern}")


def _skip(reason: str, **kwargs) -> EntryDecision:
    """Convenience constructor for skip decisions."""
    return EntryDecision(
        action="skip",
        entry_price=None,
        stop_price=None,
        reason=reason,
        bars_waited=kwargs.get("bars_waited", 0),
        touch_idx=kwargs.get("touch_idx"),
        entry_idx=kwargs.get("entry_idx"),
    )
