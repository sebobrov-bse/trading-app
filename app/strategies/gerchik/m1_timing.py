"""M1 timing: does the limit order fill inside the БПУ2 M5-bar?

БПУ2 is an M5-bar (5 minutes). A limit order is placed at:
    SHORT: entry = level - luff
    LONG:  entry = level + luff

Only the M1 bars INSIDE bpu2 can fill it. Two modes:

- strict (default): check ONLY the last M1 bar. Rationale: we cannot
  place the order before the M5 bar closes, so only the very end of
  the bar is realistic. Aggressive but no look-ahead.

- permissive: check ALL M1 bars inside bpu2. Overestimates fills
  (in reality we'd have to place the order at the start of bpu2,
  which is impossible in our pipeline). For A/B comparison only.

Also checks that bpu2 itself did not break the level:
    SHORT: bpu2.high > level  -> MODEL_BROKEN
    LONG:  bpu2.low < level   -> MODEL_BROKEN
"""

import logging
from typing import Literal

logger = logging.getLogger(__name__)

Direction = Literal["LONG", "SHORT"]
FillStatus = Literal["FILLED", "NOT_FILLED", "MODEL_BROKEN"]
TimingMode = Literal["strict", "permissive"]


def check_m1_fill(
    bpu2_bar: dict,
    m1_bars_inside_bpu2: list[dict],
    level: float,
    luff: float,
    direction: Direction,
    mode: TimingMode = "strict",
) -> tuple[FillStatus, dict | None]:
    """Check if a limit order at level±luff would fill inside bpu2.

    Returns:
        (status, fill_info) where:
        - status == "FILLED": fill_info = {"fill_price": float, "fill_bar_idx": int}
        - status == "NOT_FILLED": fill_info = None
        - status == "MODEL_BROKEN": fill_info = None
    """
    if mode not in ("strict", "permissive"):
        raise ValueError(f"mode must be 'strict' or 'permissive', got {mode!r}")

    # --- Step 1: check bpu2 didn't break the level ---
    bpu2_high = float(bpu2_bar["high"])
    bpu2_low = float(bpu2_bar["low"])
    if direction == "SHORT" and bpu2_high > level:
        return "MODEL_BROKEN", None
    if direction == "LONG" and bpu2_low < level:
        return "MODEL_BROKEN", None

    if not m1_bars_inside_bpu2:
        return "NOT_FILLED", None

    # --- Step 2: pick M1 bars to check ---
    if mode == "strict":
        candidates = [(len(m1_bars_inside_bpu2) - 1, m1_bars_inside_bpu2[-1])]
    else:  # permissive
        candidates = list(enumerate(m1_bars_inside_bpu2))

    # --- Step 3: check limit touch ---
    if direction == "SHORT":
        limit_price = level - luff
        for idx, bar in candidates:
            if float(bar["high"]) >= limit_price:
                return "FILLED", {
                    "fill_price": limit_price,
                    "fill_bar_idx": idx,
                }
        return "NOT_FILLED", None

    # LONG
    limit_price = level + luff
    for idx, bar in candidates:
        if float(bar["low"]) <= limit_price:
            return "FILLED", {
                "fill_price": limit_price,
                "fill_bar_idx": idx,
            }
    return "NOT_FILLED", None
