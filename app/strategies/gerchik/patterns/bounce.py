"""Bounce pattern: price touches a level and reverses.

For long (level is support):
- Touch:  low[i] <= level <= high[i]
- Bounce: close[i] >= level + min_bounce_atr * atr_m1  -> enter_long
- Stop:   level - stop_atr * atr_m1
- Skip:   close[i] < level - max_deviation_atr * atr_m1 (broke through)

For short (level is resistance): mirrored.

After touch, wait up to `m1_max_wait_bars` bars for the bounce to
confirm; on timeout return skip with reason='timeout_after_touch'.
"""

import logging

import pandas as pd

from app.strategies.gerchik.config import GerchikConfig
from app.strategies.gerchik.timing import EntryDecision

logger = logging.getLogger(__name__)


def _skip(
    reason: str,
    bars_waited: int = 0,
    touch_idx: int | None = None,
    entry_idx: int | None = None,
) -> EntryDecision:
    return EntryDecision(
        action="skip",
        entry_price=None,
        stop_price=None,
        reason=reason,
        bars_waited=bars_waited,
        touch_idx=touch_idx,
        entry_idx=entry_idx,
    )


def bounce_entry(
    df: pd.DataFrame,
    level_price: float,
    direction: str,
    atr_m1: float,
    config: GerchikConfig,
) -> EntryDecision:
    """Scan M1 bars for the first bounce off `level_price`.

    `df` is expected to be already normalized (lowercase cols, sorted).
    """
    if df is None or len(df) == 0:
        return _skip("empty_bars")
    if atr_m1 <= 0:
        return _skip("atr_zero")

    highs = df["high"].to_numpy(dtype=float)
    lows = df["low"].to_numpy(dtype=float)
    closes = df["close"].to_numpy(dtype=float)
    n = len(df)

    min_bounce = config.m1_bounce_min_atr * atr_m1
    stop_buffer = config.m1_bounce_stop_atr * atr_m1
    max_deviation = config.m1_bounce_max_deviation_atr * atr_m1

    touch_idx: int | None = None

    for i in range(n):
        # Find first touch of the level.
        if touch_idx is None:
            if lows[i] <= level_price <= highs[i]:
                touch_idx = i
            else:
                continue

        bars_waited = i - touch_idx
        if bars_waited > config.m1_max_wait_bars:
            return _skip(
                "timeout_after_touch",
                bars_waited=bars_waited,
                touch_idx=touch_idx,
                entry_idx=i,
            )

        c = closes[i]

        if direction == "long":
            # Price broke below the level -> this is a breakdown, not a bounce.
            if c < level_price - max_deviation:
                return _skip(
                    "price_broke_below_level",
                    bars_waited=bars_waited,
                    touch_idx=touch_idx,
                    entry_idx=i,
                )
            # Bounce confirmed?
            if c >= level_price + min_bounce:
                return EntryDecision(
                    action="enter_long",
                    entry_price=float(c),
                    stop_price=float(level_price - stop_buffer),
                    reason="bounce_confirmed",
                    bars_waited=bars_waited,
                    touch_idx=touch_idx,
                    entry_idx=i,
                )
        else:  # short
            if c > level_price + max_deviation:
                return _skip(
                    "price_broke_above_level",
                    bars_waited=bars_waited,
                    touch_idx=touch_idx,
                    entry_idx=i,
                )
            if c <= level_price - min_bounce:
                return EntryDecision(
                    action="enter_short",
                    entry_price=float(c),
                    stop_price=float(level_price + stop_buffer),
                    reason="bounce_confirmed",
                    bars_waited=bars_waited,
                    touch_idx=touch_idx,
                    entry_idx=i,
                )

    if touch_idx is None:
        return _skip("no_touch")
    return _skip(
        "end_of_bars",
        bars_waited=n - 1 - touch_idx,
        touch_idx=touch_idx,
        entry_idx=n - 1,
    )
