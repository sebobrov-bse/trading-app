"""Risk-based position sizing.

Given capital, risk per trade (%), entry price, and stop price, returns
the position size such that a stop hit loses exactly the risk amount.
"""

from decimal import Decimal

from app.risk.config import RiskConfig


def calculate_size(
    capital: float,
    entry_price: float,
    stop_price: float,
    config: RiskConfig,
    contract_multiplier: Decimal | float | None = None,
) -> int:
    """Return position size in contracts/shares.

    Applies:
    - risk-based sizing (risk_amount / risk_per_unit);
    - min stop distance (entry * min_stop_distance_pct);
    - max position value (capital * max_position_value_pct / 100).
    """
    if entry_price <= 0:
        return 0

    risk_amount = capital * config.risk_per_trade_pct / 100.0
    if risk_amount <= 0:
        return 0

    # Enforce min stop distance.
    min_distance = entry_price * config.min_stop_distance_pct
    stop_distance = abs(entry_price - stop_price)
    effective_distance = max(stop_distance, min_distance)
    if effective_distance <= 0:
        return 0

    raw_size = risk_amount / effective_distance

    # For futures, convert to contracts.
    if contract_multiplier is not None and contract_multiplier > 0:
        raw_size = raw_size / float(contract_multiplier)

    # Cap by max position value.
    max_value = capital * config.max_position_value_pct / 100.0
    max_size_by_value = max_value / entry_price
    if contract_multiplier is not None and contract_multiplier > 0:
        max_size_by_value = max_size_by_value / float(contract_multiplier)

    return int(min(raw_size, max_size_by_value))
