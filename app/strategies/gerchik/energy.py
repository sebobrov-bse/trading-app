"""Energy evaluation for the Gerchik system.

Determines the market state in the bars preceding a level:
- ACCUMULATION: pct_small >= 0.6 (many tight bars).
- DISTRIBUTION: pct_big >= 0.4 OR exhaustion (price tested the level
                and then retreated from it).
- COMPRESSION:  narrowing ranges (2 of 3 conditions).
- NEUTRAL: no clear signal.

Priority: DISTRIBUTION > COMPRESSION > ACCUMULATION > NEUTRAL.
Rationale: exhaustion is the strongest 'get out' signal; compression
is a more specific form of accumulation.
"""

import logging
from dataclasses import dataclass
from enum import Enum

import numpy as np
import pandas as pd

from app.strategies.gerchik.config import GerchikConfig

logger = logging.getLogger(__name__)


class EnergyContext(str, Enum):
    ACCUMULATION = "accumulation"
    DISTRIBUTION = "distribution"
    COMPRESSION = "compression"
    NEUTRAL = "neutral"


@dataclass(frozen=True)
class EnergyResult:
    context: EnergyContext
    window: int
    pct_small: float
    pct_big: float
    has_compression: bool
    has_exhaustion: bool


def _detect_compression(
    ranges: np.ndarray,
    highs: np.ndarray,
    lows: np.ndarray,
) -> bool:
    """2 of 3 conditions: overall narrowing, last<first, extremes converging."""
    n = len(ranges)
    if n < 3:
        return False

    hits = 0

    # C1: overall range decreased, and mostly monotone-narrowing.
    if ranges[0] > ranges[-1] * 1.2:
        narrowing = sum(1 for k in range(1, n) if ranges[k] <= ranges[k - 1] * 1.1)
        if narrowing >= n - 2:
            hits += 1

    k = min(3, n // 2)
    if k >= 1 and n >= 2 * k:
        # C2: last k avg < first k avg by 20%.
        first_avg = float(np.mean(ranges[:k]))
        last_avg = float(np.mean(ranges[-k:]))
        if first_avg > 0 and last_avg < first_avg * 0.8:
            hits += 1

        # C3: extremes converge.
        early = float(np.max(highs[:k]) - np.min(lows[:k]))
        late = float(np.max(highs[-k:]) - np.min(lows[-k:]))
        if early > 0 and late < early * 0.7:
            hits += 1

    return hits >= 2


def evaluate_energy(
    bars_before_level: pd.DataFrame,
    level_price: float,
    atr: float,
    config: GerchikConfig,
) -> EnergyResult:
    """Evaluate energy state in the bars before a level.

    `bars_before_level` — slice of D1 bars immediately preceding
    the bar where the level is being considered. Must have
    columns open, high, low, close.
    """
    empty = EnergyResult(EnergyContext.NEUTRAL, 0, 0.0, 0.0, False, False)
    if len(bars_before_level) == 0 or atr <= 0:
        return empty

    last_close = float(bars_before_level["close"].iloc[-1])
    distance = abs(last_close - level_price)

    # Adaptive window: close to level -> short window (captures the
    # immediate 'what is happening now'); far away -> long window.
    if distance < 0.5 * atr:
        window = config.energy_window_min
    else:
        window = config.energy_window_max

    window = min(window, len(bars_before_level))
    bars = bars_before_level.tail(window)

    highs = bars["high"].to_numpy(dtype=float)
    lows = bars["low"].to_numpy(dtype=float)
    closes = bars["close"].to_numpy(dtype=float)
    ranges = highs - lows
    n = len(ranges)
    if n == 0:
        return empty

    small_count = int((ranges < config.energy_small_k * atr).sum())
    big_count = int((ranges > config.energy_big_k * atr).sum())
    pct_small = small_count / n
    pct_big = big_count / n

    has_compression = _detect_compression(ranges, highs, lows)

    # Exhaustion: the level was tested AND the last close has moved
    # away from it by more than the threshold.
    tested = bool(np.any((lows <= level_price) & (highs >= level_price)))
    if tested:
        retreat = abs(float(closes[-1]) - level_price)
        has_exhaustion = retreat > config.energy_exhaustion_atr * atr
    else:
        has_exhaustion = False

    # Priority: DISTRIBUTION > COMPRESSION > ACCUMULATION > NEUTRAL.
    if has_exhaustion or pct_big >= config.energy_distribution_pct:
        context = EnergyContext.DISTRIBUTION
    elif has_compression:
        context = EnergyContext.COMPRESSION
    elif pct_small >= config.energy_accumulation_pct:
        context = EnergyContext.ACCUMULATION
    else:
        context = EnergyContext.NEUTRAL

    return EnergyResult(
        context=context,
        window=n,
        pct_small=pct_small,
        pct_big=pct_big,
        has_compression=has_compression,
        has_exhaustion=has_exhaustion,
    )
