"""Contract specification for stocks and futures.

Stores per-instrument constants: contract multiplier, tick size,
expiration date, underlying asset. Used for correct PnL calculation
and continuous series rolling.
"""

from datetime import datetime
from decimal import Decimal

from sqlalchemy import (
    Boolean,
    DateTime,
    Integer,
    Numeric,
    String,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class InstrumentSpec(Base):
    """Per-instrument static data (multiplier, tick size, expiration)."""

    __tablename__ = "instrument_specs"
    __table_args__ = (UniqueConstraint("symbol", "asset_type", name="uq_spec_symbol_asset"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    symbol: Mapped[str] = mapped_column(String(20), nullable=False, index=True)
    asset_type: Mapped[str] = mapped_column(String(10), nullable=False)

    display_name: Mapped[str | None] = mapped_column(String(200), nullable=True)
    contract_multiplier: Mapped[Decimal | None] = mapped_column(Numeric(18, 6), nullable=True)
    tick_size: Mapped[Decimal | None] = mapped_column(Numeric(18, 6), nullable=True)
    tick_value: Mapped[Decimal | None] = mapped_column(Numeric(18, 6), nullable=True)
    expiration_date: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    base_asset: Mapped[str | None] = mapped_column(String(20), nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)

    def __repr__(self) -> str:
        return (
            f"<InstrumentSpec {self.symbol} ({self.asset_type}) "
            f"mult={self.contract_multiplier} exp={self.expiration_date}>"
        )
