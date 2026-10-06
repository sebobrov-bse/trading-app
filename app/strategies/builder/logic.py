"""Logical combination of conditions (AND, OR)."""

from collections.abc import Callable
from typing import Any


def _and(conditions: list[Any]) -> Any:
    """All conditions must be true. Short-circuits on False."""
    if not conditions:
        return False
    result = conditions[0]
    for c in conditions[1:]:
        result = result & c
    return result


def _or(conditions: list[Any]) -> Any:
    """At least one condition must be true."""
    if not conditions:
        return False
    result = conditions[0]
    for c in conditions[1:]:
        result = result | c
    return result


LOGIC_REGISTRY: dict[str, Callable[[list[Any]], Any]] = {
    "AND": _and,
    "OR": _or,
}
