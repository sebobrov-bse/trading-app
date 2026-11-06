"""Two-step ATR and path_ratio for the Gerchik system.

Step 1: prelim = median(ranges) over atr_period bars.
Step 2: filter out ranges outside [small_k * prelim, big_k * prelim].
Step 3: final = mean(filtered); fallback to prelim if too few survive.

Why median first: a single paranormal bar (range = 5×normal) skews the
mean, but barely moves the median. So median is the anchor, and the
filter removes the very bars that would have skewed the mean.
"""

import logging
from dataclasses import dataclass

import numpy as np
import pandas as pd

from app.strategies.gerchik.config import GerchikConfig

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class ATRResult:
    """Result of the two-step ATR calculation."""

    value: float  # final ATR used in downstream logic
    prelim_value: float  # median-based preliminary ATR
    filtered_bars: int  # how many bars survived the filter
    used_fallback: bool  # True if we had to fall back to prelim


def calculate_clean_atr(
    daily_bars: pd.DataFrame,
    config: GerchikConfig,
) -> ATRResult:
    """Compute a robust ATR from the last `atr_period` daily bars.

    `daily_bars` must be sorted ascending by timestamp, with columns
    high, low. Only the last `atr_period` rows are used.

    Returns ATRResult; if there is not enough data, returns ATRResult
    with value=nan and used_fallback=True.
    """
    if len(daily_bars) == 0:
        logger.warning("calculate_clean_atr: empty input")
        return ATRResult(
            value=float("nan"), prelim_value=float("nan"), filtered_bars=0, used_fallback=True
        )

    tail = daily_bars.tail(config.atr_period)
    ranges = (tail["high"] - tail["low"]).to_numpy(dtype=float)

    if len(ranges) == 0:
        return ATRResult(
            value=float("nan"), prelim_value=float("nan"), filtered_bars=0, used_fallback=True
        )

    # Step 1: robust anchor — median.
    prelim = float(np.median(ranges))

    if not np.isfinite(prelim) or prelim <= 0:
        return ATRResult(
            value=prelim, prelim_value=prelim, filtered_bars=len(ranges), used_fallback=True
        )

    # Step 2: drop micro-bars and paranormal bars.
    lo_bound = config.atr_small_k * prelim
    hi_bound = config.atr_big_k * prelim
    filtered = ranges[(ranges >= lo_bound) & (ranges <= hi_bound)]

    # Step 3: mean of filtered; fallback to prelim.
    if len(filtered) < config.atr_fallback_min_bars:
        logger.debug(
            "ATR fallback: only %d bars survived filter (need %d)",
            len(filtered),
            config.atr_fallback_min_bars,
        )
        return ATRResult(
            value=prelim, prelim_value=prelim, filtered_bars=len(filtered), used_fallback=True
        )

    final = float(np.mean(filtered))
    return ATRResult(
        value=final, prelim_value=prelim, filtered_bars=len(filtered), used_fallback=False
    )


def calculate_path_ratio(
    current_price: float,
    prev_close: float,
    direction: str,
    atr: float,
) -> float:
    """How far the price moved from prev_close, in ATR units.

    direction: "long" — measured upward (current - prev_close) / atr.
               "short" — measured downward (prev_close - current) / atr.

    Returns a signed float. Can be negative if the price moved against
    the direction (e.g. long direction but current < prev_close).
    Returns 0.0 if atr <= 0.
    """
    if atr <= 0 or not np.isfinite(atr):
        return 0.0

    if direction == "long":
        return (current_price - prev_close) / atr
    if direction == "short":
        return (prev_close - current_price) / atr
    raise ValueError(f"direction must be 'long' or 'short', got {direction!r}")


def passes_atr_filter(path_ratio: float, config: GerchikConfig) -> bool:
    """True if |path_ratio| >= atr_filter_threshold (default 75% ATR).

    Used to filter out 'too far already moved' days. Also true if
    allow_ath_override and the caller decides this is an ATH case
    (handled upstream, not here).
    """
    return abs(path_ratio) >= config.atr_filter_threshold
