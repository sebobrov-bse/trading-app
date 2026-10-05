"""Pydantic models for MOEX futures metadata."""

from datetime import date
from decimal import Decimal

from pydantic import BaseModel, Field


# Map from MOEX ASSETCODE (in futures/securities.json) to the underlying
# stock ticker (in candles.symbol). For futures on indices/commodities,
# the asset code is used as-is.
FUTURES_BASE_MAP: dict[str, str] = {
    "SBRF": "SBER",
    "GAZR": "GAZP",
    "LKOH": "LKOH",
    "ROSN": "ROSN",
    "BR": "BR",
    "RTS": "RTS",
    "SI": "SI",
    "GOLD": "GOLD",
    "SILV": "SILV",
}


class FuturesContract(BaseModel):
    """One active futures contract from MOEX ISS."""

    secid: str = Field(..., description="MOEX internal code, e.g. SRH7")
    shortname: str = Field(..., description="Trade name, e.g. SBRF-3.27")
    asset_code: str = Field(..., description="Base asset code, e.g. SBRF")
    base_asset: str = Field(..., description="Underlying stock/index ticker")
    expiration_date: date = Field(..., description="Last trade date")
    contract_multiplier: Decimal = Field(..., gt=0)
    tick_size: Decimal = Field(..., gt=0)
    tick_value: Decimal = Field(..., ge=0)

    @property
    def display_name(self) -> str:
        return f"{self.shortname} ({self.secid})"
