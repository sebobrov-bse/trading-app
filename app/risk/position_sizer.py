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

    For futures, pass contract_multiplier (e.g. 100 for SBRF) to convert
    the number of base units into the number of contracts.
    """
    if entry_price <= 0:
        return 0

    risk_amount = capital * config.risk_per_trade_pct / 100.0
    if risk_amount <= 0:
        return 0

    risk_per_unit = abs(entry_price - stop_price)
    if risk_per_unit <= 0:
        return 0

    raw_size = risk_amount / risk_per_unit

    # For futures, divide by multiplier. Example: raw_size=137 base units,
    # multiplier=100 → 1 contract.
    if contract_multiplier is not None and contract_multiplier > 0:
        multiplier_f = float(contract_multiplier)
        raw_size = raw_size / multiplier_f

    return int(raw_size)
