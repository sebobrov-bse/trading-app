"""Stop-loss movement logic for the Levin system.

Three variants:
- fixed:          stop does not move until TP/SL is hit.
- trailing_r:     stop moves at 1/3 and 2/3 of the way to TP.
- dynamic_minmax: stop follows previous bar's low (long) / high (short),
                  moving only in the direction of profit.

The core function `compute_new_stop` is pure and testable without
Backtrader. The `StopManager` wrapper (used by the strategy) keeps
per-trade state and calls this function on each bar.
"""

from dataclasses import dataclass
from typing import Literal

Direction = Literal["long", "short"]
StopVariant = Literal["fixed", "trailing_r", "dynamic_minmax"]


def compute_new_stop(
    variant: StopVariant,
    direction: Direction,
    entry_price: float,
    initial_stop: float,
    take_profit: float,
    current_price: float,
    current_low: float,
    current_high: float,
    current_stop: float,
) -> float | None:
    """Return the new stop price, or None if no change is needed.

    Args:
        variant: "fixed" | "trailing_r" | "dynamic_minmax".
        direction: "long" | "short".
        entry_price: trade entry price.
        initial_stop: the stop at the time of entry.
        take_profit: target price.
        current_price: current bar's close.
        current_low: current bar's low (used by dynamic_minmax for long).
        current_high: current bar's high (used by dynamic_minmax for short).
        current_stop: the stop price currently placed.

    Returns:
        A new stop price if it should be moved, otherwise None.
    """
    if variant == "fixed":
        return None

    if variant == "trailing_r":
        return _trailing_r(
            direction,
            entry_price,
            initial_stop,
            take_profit,
            current_price,
            current_stop,
        )

    if variant == "dynamic_minmax":
        return _dynamic_minmax(
            direction,
            current_low,
            current_high,
            current_stop,
        )

    raise ValueError(f"Unknown stop variant: {variant}")


def _trailing_r(
    direction: Direction,
    entry_price: float,
    initial_stop: float,
    take_profit: float,
    current_price: float,
    current_stop: float,
) -> float | None:
    """Move stop to 1/3 / 2/3 of the distance to TP.

    For a long:
        if price >= entry + 1/3 * (TP - entry): stop = entry + 1/3 * (TP - entry)
        if price >= entry + 2/3 * (TP - entry): stop = entry + 2/3 * (TP - entry)

    Only ever moves the stop in the profit direction (long: up, short: down).
    """
    risk = abs(take_profit - entry_price)
    if risk <= 0:
        return None

    if direction == "long":
        dist_to_tp = take_profit - entry_price
        if dist_to_tp <= 0:
            return None

        # Thresholds: 1/3 and 2/3 of the distance to TP.
        t1 = entry_price + dist_to_tp * (1.0 / 3.0)
        t2 = entry_price + dist_to_tp * (2.0 / 3.0)

        candidate: float | None = None
        if current_price >= t2:
            candidate = t2
        elif current_price >= t1:
            candidate = t1

        if candidate is None:
            return None
        if candidate <= current_stop:
            return None
        return candidate

    # Short
    dist_to_tp = entry_price - take_profit
    if dist_to_tp <= 0:
        return None

    t1 = entry_price - dist_to_tp * (1.0 / 3.0)
    t2 = entry_price - dist_to_tp * (2.0 / 3.0)

    candidate = None
    if current_price <= t2:
        candidate = t2
    elif current_price <= t1:
        candidate = t1

    if candidate is None:
        return None
    if candidate >= current_stop:
        return None
    return candidate


def _dynamic_minmax(
    direction: Direction,
    current_low: float,
    current_high: float,
    current_stop: float,
) -> float | None:
    """Trail stop by previous bar's extreme.

    Long: stop rises to the previous bar's LOW (never falls).
    Short: stop falls to the previous bar's HIGH (never rises).
    """
    if direction == "long":
        # Trailing long: stop can only move up.
        if current_low > current_stop:
            return current_low
        return None

    # Short: stop can only move down.
    if current_high < current_stop:
        return current_high
    return None


# ---------------------------------------------------------------------------
#  Stateful wrapper for the strategy
# ---------------------------------------------------------------------------


@dataclass
class StopManager:
    """Per-trade state for stop movement.

    Instantiated when a position opens, reset when it closes.
    """

    variant: StopVariant
    direction: Direction
    entry_price: float
    initial_stop: float
    take_profit: float
    current_stop: float

    def update(
        self,
        current_price: float,
        current_low: float,
        current_high: float,
    ) -> float | None:
        """Return a new stop if it should move, else None."""
        new_stop = compute_new_stop(
            variant=self.variant,
            direction=self.direction,
            entry_price=self.entry_price,
            initial_stop=self.initial_stop,
            take_profit=self.take_profit,
            current_price=current_price,
            current_low=current_low,
            current_high=current_high,
            current_stop=self.current_stop,
        )
        if new_stop is not None:
            self.current_stop = new_stop
        return new_stop
