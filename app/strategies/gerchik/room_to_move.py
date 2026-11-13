"""Room-to-move filter: is there enough space before the next level?

For a LONG entry at price E with stop size S, the nearest resistance
level R above E must satisfy:

    R - E >= room_to_move_multiplier * S

Otherwise the take-profit (at E + 3*S) would "run into" that level
and get rejected before reaching the target.

The multiplier is 4x (not 3x) — buffer so the TP isn't placed right
at the level (level touches often trigger bounces BEFORE the level
is actually reached).
"""

import logging

from app.strategies.gerchik.config import GerchikConfig

logger = logging.getLogger(__name__)


def find_next_level(
    current_level: float,
    direction: str,
    all_levels: list[float],
) -> float | None:
    """Find the nearest level in the direction of the trade.

    For LONG:  nearest level ABOVE current_level  (resistance).
    For SHORT: nearest level BELOW current_level  (support).

    Returns None if no level exists in that direction (trade is
    allowed without room check — probably new ATH/ATL).
    """
    if not all_levels:
        return None

    others = [p for p in all_levels if p != current_level]
    if not others:
        return None

    if direction == "long":
        above = [p for p in others if p > current_level]
        return min(above) if above else None
    if direction == "short":
        below = [p for p in others if p < current_level]
        return max(below) if below else None
    raise ValueError(f"direction must be 'long' or 'short', got {direction!r}")


def check_room_to_move(
    entry: float,
    stop_size: float,
    next_level: float | None,
    config: GerchikConfig,
) -> bool:
    """Return True if there is enough room to reach the take-profit.

    `next_level=None` -> True (no resistance/support in the way).

    Otherwise: |next_level - entry| >= multiplier * stop_size.
    """
    if next_level is None:
        return True
    if stop_size <= 0:
        return False

    room = abs(next_level - entry)
    threshold = config.room_to_move_multiplier * stop_size
    return room >= threshold
