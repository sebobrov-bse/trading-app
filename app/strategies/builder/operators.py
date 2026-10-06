"""Registry of comparison operators.

Each operator maps to a function evaluate(left, right) -> boolean-like
Backtrader line.
"""

from collections.abc import Callable
from typing import Any

import backtrader as bt


# ---- evaluators ----


def _gt(left: Any, right: Any) -> Any:
    return left > right


def _lt(left: Any, right: Any) -> Any:
    return left < right


def _ge(left: Any, right: Any) -> Any:
    return left >= right


def _le(left: Any, right: Any) -> Any:
    return left <= right


def _eq(left: Any, right: Any) -> Any:
    return left == right


def _ne(left: Any, right: Any) -> Any:
    return left != right


def _cross_above(left: Any, right: Any) -> Any:
    """True on the bar where `left` crosses `right` from below."""
    return bt.indicators.CrossOver(left, right) > 0


def _cross_below(left: Any, right: Any) -> Any:
    """True on the bar where `left` crosses `right` from above."""
    return bt.indicators.CrossOver(left, right) < 0


OPERATOR_REGISTRY: dict[str, Callable[[Any, Any], Any]] = {
    ">": _gt,
    "<": _lt,
    ">=": _ge,
    "<=": _le,
    "==": _eq,
    "!=": _ne,
    "cross_above": _cross_above,
    "cross_below": _cross_below,
}
