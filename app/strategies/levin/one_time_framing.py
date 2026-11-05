"""One-Time Framing detector.

One-Time Framing (OTF) is a Market Profile concept: a strictly
sequential framing where each bar breaks the previous one in the
direction of the trend.

For LONG (uptrend):
    low[t-3] > low[t-2]  and  low[t-2] < low[t-1] < low[t]

For SHORT (downtrend):
    high[t-3] < high[t-2]  and  high[t-2] > high[t-1] > high[t]

The functions take a Backtrader data feed and the current bar index
(len(data) - 1) and return True/False.
"""

from typing import Protocol


class _DataLike(Protocol):
    """Minimal Backtrader-like interface for testing."""

    high: ...
    low: ...


def is_otf_up(data, i: int) -> bool:
    """Return True if bars (i-3..i) form an up One-Time Frame.

    Requires at least 4 bars. Uses low prices.
    """
    if i < 3:
        return False
    try:
        # Backtrader indexing: data.low[-k] = k bars back.
        lo_t3 = float(data.low[-3])
        lo_t2 = float(data.low[-2])
        lo_t1 = float(data.low[-1])
        lo_t0 = float(data.low[0])
    except (IndexError, TypeError):
        return False

    return lo_t3 > lo_t2 and lo_t2 < lo_t1 < lo_t0


def is_otf_down(data, i: int) -> bool:
    """Return True if bars (i-3..i) form a down One-Time Frame.

    Requires at least 4 bars. Uses high prices.
    """
    if i < 3:
        return False
    try:
        hi_t3 = float(data.high[-3])
        hi_t2 = float(data.high[-2])
        hi_t1 = float(data.high[-1])
        hi_t0 = float(data.high[0])
    except (IndexError, TypeError):
        return False

    return hi_t3 < hi_t2 and hi_t2 > hi_t1 > hi_t0
