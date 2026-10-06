"""Registry of signal filters.

Filters are applied BEFORE entry signals. They gate the signal:
if any filter is False, entry is skipped for that bar.
"""

from dataclasses import dataclass, field
from typing import Any


@dataclass
class FilterSpec:
    """Spec for a filter."""

    name: str
    params: dict[str, Any] = field(default_factory=dict)
    description: str = ""


FILTER_REGISTRY: dict[str, FilterSpec] = {
    "volume": FilterSpec(
        "volume",
        {"sma_period": 20, "multiplier": 1.5},
        "Volume > SMA(volume) * multiplier",
    ),
    "time": FilterSpec(
        "time",
        {"sessions": ["morning", "afternoon"]},
        "Trade only during given sessions",
    ),
    "atr": FilterSpec(
        "atr",
        {"period": 14, "min_value": 0.0},
        "ATR(period) > min_value",
    ),
    "day_of_week": FilterSpec(
        "day_of_week",
        {"days": ["Mon", "Tue", "Wed", "Thu", "Fri"]},
        "Trade only on given weekdays",
    ),
}
