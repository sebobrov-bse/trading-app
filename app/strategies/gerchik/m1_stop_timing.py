"""M1 stop-order trigger: does the pending Stop order fill inside M5?

A Stop order is placed at setup.stop_order_price (level ± offset).
It's active for the whole M5 window after setup detection.

Modes:
- "any" (default for Stop orders): check every M1 bar inside M5.
  Correct because the order is live and any M1 high/low can trigger it.
- "strict": check only the last M1 bar (used for A/B comparison with
  limit orders — for Stop orders this underestimates fills).

Fill price:
- Normal case: stop_order_price (order executes at its trigger price).
- Gap case: if the M1 bar OPENS already beyond the stop, fill at open
  (we can't get a better price than the market provides).
"""

import logging
from typing import Literal

from app.strategies.gerchik.breakout import BreakoutSetup

logger = logging.getLogger(__name__)

TimingMode = Literal["any", "strict"]


def check_stop_order_trigger(
    setup: BreakoutSetup,
    m1_bars_inside_m5: list[dict],
    mode: TimingMode = "any",
) -> tuple[bool, float | None]:
    """Check if the pending Stop order fills inside the M5 window.

    Returns:
        (triggered, fill_price):
        - (True, fill_price) if the order fills.
        - (False, None) otherwise.

    `m1_bars_inside_m5` is a list of dicts with keys:
        "open", "high", "low", "close" (floats).
    """
    if mode not in ("any", "strict"):
        raise ValueError(f"mode must be 'any' or 'strict', got {mode!r}")

    if not m1_bars_inside_m5:
        return False, None

    candidates: list[dict]
    if mode == "strict":
        candidates = [m1_bars_inside_m5[-1]]
    else:  # "any"
        candidates = list(m1_bars_inside_m5)

    trigger_price = setup.stop_order_price

    for bar in candidates:
        bar_open = float(bar["open"])
        bar_high = float(bar["high"])
        bar_low = float(bar["low"])

        if setup.direction == "LONG":
            # Stop-buy triggers when price rises to trigger_price.
            if bar_high >= trigger_price:
                # Gap up: bar opened already above trigger -> fill at open.
                if bar_open > trigger_price:
                    return True, bar_open
                return True, trigger_price
        else:  # SHORT
            # Stop-sell triggers when price falls to trigger_price.
            if bar_low <= trigger_price:
                # Gap down: bar opened already below trigger -> fill at open.
                if bar_open < trigger_price:
                    return True, bar_open
                return True, trigger_price

    return False, None
