"""Limit Player (LP) pattern: false breakout that reverses.

For long (level is support, price breaks DOWN then returns UP):
- Break:     close[i] < level - break_atr * atr_m1
- Track:     deepest low after the break (the LP 'sweep' low)
- Return:    close[j] >= level + return_atr * atr_m1
- Entry:     long at that close
- Stop:      deepest_low - stop_atr * atr_m1
- Skip:      timeout after break

For short: mirrored (level is resistance, price breaks UP then returns
DOWN).

The LP 'stop hunt' — price wicks below support to grab stops, then
reverses. The deepest low after the break IS the stop-loss zone: the
big players pushed price there, then reversed. Placing our stop just
beyond that low is the classic LP setup.
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


def limit_player_entry(
    df: pd.DataFrame,
    level_price: float,
    direction: str,
    atr_m1: float,
    config: GerchikConfig,
) -> EntryDecision:
    """Scan M1 bars for a false breakout that reverses (LP setup)."""
    if df is None or len(df) == 0:
        return _skip("empty_bars")
    if atr_m1 <= 0:
        return _skip("atr_zero")

    highs = df["high"].to_numpy(dtype=float)
    lows = df["low"].to_numpy(dtype=float)
    closes = df["close"].to_numpy(dtype=float)
    n = len(df)

    break_amount = config.m1_lp_break_atr * atr_m1
    return_amount = config.m1_limit_player_return_atr * atr_m1
    stop_buffer = config.m1_lp_stop_atr * atr_m1

    broken_idx: int | None = None
    extreme: float | None = None  # deepest low (long) / highest high (short)

    for i in range(n):
        if broken_idx is None:
            # Detect the false break.
            if direction == "long" and closes[i] < level_price - break_amount:
                broken_idx = i
                extreme = float(lows[i])
            elif direction == "short" and closes[i] > level_price + break_amount:
                broken_idx = i
                extreme = float(highs[i])
            continue

        bars_waited = i - broken_idx
        if bars_waited > config.m1_max_wait_bars:
            return _skip(
                "timeout_after_break",
                bars_waited=bars_waited,
                touch_idx=broken_idx,
                entry_idx=i,
            )

        if direction == "long":
            # Track the LP sweep low.
            if lows[i] < extreme:
                extreme = float(lows[i])
            # Return above level confirms the false breakout.
            if closes[i] >= level_price + return_amount:
                return EntryDecision(
                    action="enter_long",
                    entry_price=float(closes[i]),
                    stop_price=float(extreme - stop_buffer),
                    reason="lp_return_confirmed",
                    bars_waited=bars_waited,
                    touch_idx=broken_idx,
                    entry_idx=i,
                )
        else:  # short
            if highs[i] > extreme:
                extreme = float(highs[i])
            if closes[i] <= level_price - return_amount:
                return EntryDecision(
                    action="enter_short",
                    entry_price=float(closes[i]),
                    stop_price=float(extreme + stop_buffer),
                    reason="lp_return_confirmed",
                    bars_waited=bars_waited,
                    touch_idx=broken_idx,
                    entry_idx=i,
                )

    if broken_idx is None:
        return _skip("no_false_break")
    return _skip(
        "end_of_bars",
        bars_waited=n - 1 - broken_idx,
        touch_idx=broken_idx,
        entry_idx=n - 1,
    )
