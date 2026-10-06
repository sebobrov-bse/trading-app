"""Logical combination of conditions (AND, OR).

Backtrader lines do not support `&` / `|` operators. We use the
built-in `bt.And` and `bt.Or` indicators instead, which accept two
lines and return a boolean-like line.
"""

from collections.abc import Callable
from typing import Any

import backtrader as bt


def _and(conditions: list[Any]) -> Any:
    """All conditions must be true (element-wise)."""
    if not conditions:
        return False
    if len(conditions) == 1:
        return conditions[0]
    result = bt.And(conditions[0], conditions[1])
    for c in conditions[2:]:
        result = bt.And(result, c)
    return result


def _or(conditions: list[Any]) -> Any:
    """At least one condition must be true (element-wise)."""
    if not conditions:
        return False
    if len(conditions) == 1:
        return conditions[0]
    result = bt.Or(conditions[0], conditions[1])
    for c in conditions[2:]:
        result = bt.Or(result, c)
    return result


LOGIC_REGISTRY: dict[str, Callable[[list[Any]], Any]] = {
    "AND": _and,
    "OR": _or,
}
