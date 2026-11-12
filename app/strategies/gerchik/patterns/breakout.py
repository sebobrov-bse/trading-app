"""Breakout pattern: price breaks through a level and holds.

For long (level is resistance being broken upwards):
- Touch:     low[i] <= level <= high[i]
- Confirm:   m1_breakout_confirm_bars consecutive closes >= level + min_atr
- Stop:      level - stop_atr * atr_m1
- Skip:      close falls below level - max_deviation (returned below)
- Skip:      timeout after touch

For short: mirrored (level is support being broken downwards).
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


def breakout_entry(
    df: pd.DataFrame,
    level_price: float,
    direction: str,
    atr_m1: float,
    config: GerchikConfig,
) -> EntryDecision:
    """Scan M1 bars for the first confirmed breakout of `level_price`."""
    if df is None or len(df) == 0:
        return _skip("empty_bars")
    if atr_m1 <= 0:
        return _skip("atr_zero")

    highs = df["high"].to_numpy(dtype=float)
    lows = df["low"].to_numpy(dtype=float)
    closes = df["close"].to_numpy(dtype=float)
    n = len(df)

    min_break = config.m1_breakout_min_atr * atr_m1
    stop_buffer = config.m1_breakout_stop_atr * atr_m1
    max_dev = config.m1_breakout_max_deviation_atr * atr_m1
    confirm_needed = config.m1_breakout_confirm_bars

    touch_idx: int | None = None
    confirm_count = 0

    for i in range(n):
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
            # Returned below level -> false breakout, LP's play, not ours.
            if c < level_price - max_dev:
                return _skip(
                    "price_returned_below_level",
                    bars_waited=bars_waited,
                    touch_idx=touch_idx,
                    entry_idx=i,
                )
            # Confirmed close above level?
            if c >= level_price + min_break:
                confirm_count += 1
                if confirm_count >= confirm_needed:
                    return EntryDecision(
                        action="enter_long",
                        entry_price=float(c),
                        stop_price=float(level_price - stop_buffer),
                        reason="breakout_confirmed",
                        bars_waited=bars_waited,
                        touch_idx=touch_idx,
                        entry_idx=i,
                    )
            else:
                # Close back below level+min_break -> reset confirmation streak.
                if c < level_price:
                    confirm_count = 0
        else:  # short
            if c > level_price + max_dev:
                return _skip(
                    "price_returned_above_level",
                    bars_waited=bars_waited,
                    touch_idx=touch_idx,
                    entry_idx=i,
                )
            if c <= level_price - min_break:
                confirm_count += 1
                if confirm_count >= confirm_needed:
                    return EntryDecision(
                        action="enter_short",
                        entry_price=float(c),
                        stop_price=float(level_price + stop_buffer),
                        reason="breakout_confirmed",
                        bars_waited=bars_waited,
                        touch_idx=touch_idx,
                        entry_idx=i,
                    )
            else:
                if c > level_price:
                    confirm_count = 0

    if touch_idx is None:
        return _skip("no_touch")
    return _skip(
        "end_of_bars",
        bars_waited=n - 1 - touch_idx,
        touch_idx=touch_idx,
        entry_idx=n - 1,
    )
