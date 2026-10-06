"""Stop-loss price factory.

Three stop types:
- "atr":     entry - atr_multiplier * ATR(period)
- "percent": entry * (1 -/+ stop_percent)
- "n_bars":  min(low[-n_bars:]) for long, max(high[-n_bars:]) for short

The factory takes the strategy (for ATR and lookback access) and the
risk config. It does NOT know about positions or orders.
"""

from typing import Literal

import backtrader as bt

from app.risk.config import RiskConfig


def calculate_stop_price(
    strategy: bt.Strategy,
    config: RiskConfig,
    entry_price: float,
    direction: Literal["long", "short"],
) -> float:
    """Return the stop-loss price for a given entry and direction."""
    if config.stop_type == "atr":
        atr = _get_atr(strategy, config.atr_period)
        distance = config.atr_multiplier * atr

    elif config.stop_type == "percent":
        distance = entry_price * config.stop_percent

    elif config.stop_type == "n_bars":
        n = config.stop_n_bars
        if direction == "long":
            lowest = min(strategy.data.low.get(size=n))
            distance = entry_price - lowest
        else:
            highest = max(strategy.data.high.get(size=n))
            distance = highest - entry_price

        # Sanity: never negative.
        distance = max(distance, entry_price * 0.001)

    else:
        raise ValueError(f"Unknown stop_type: {config.stop_type}")

    if direction == "long":
        return entry_price - distance
    else:
        return entry_price + distance


def _get_atr(strategy: bt.Strategy, period: int) -> float:
    """Return the latest ATR value, computing the indicator if needed.

    Returns 0.0 if the indicator has not warmed up yet — callers must
    treat 0.0 as "ATR not available" and skip the trade.
    """
    if not hasattr(strategy, "_risk_atr"):
        strategy._risk_atr = bt.indicators.ATR(strategy.data, period=period)
    try:
        value = strategy._risk_atr[0]
    except IndexError:
        return 0.0
    return float(value) if value == value else 0.0  # NaN guard


def calculate_stop_distance(
    strategy: bt.Strategy,
    config: RiskConfig,
    entry_price: float,
    direction: Literal["long", "short"],
) -> float:
    """Return absolute stop distance (always positive)."""
    stop = calculate_stop_price(strategy, config, entry_price, direction)
    return abs(entry_price - stop)


def calculate_take_profit_price(
    entry_price: float,
    stop_price: float,
    direction: Literal["long", "short"],
    rr: float,
) -> float:
    """Return take-profit price given R:R."""
    risk = abs(entry_price - stop_price)
    reward = risk * rr
    if direction == "long":
        return entry_price + reward
    else:
        return entry_price - reward
