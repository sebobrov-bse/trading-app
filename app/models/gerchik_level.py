"""Gerchik precomputed level snapshot for one (symbol, date).

One row = one strong level on one day, with the full context:
trend, path_ratio, energy, atr, prev_close. Written by
precompute_gerchik() and read by /gerchik/debug and (in S.2b)
by the trading strategy.

Index (symbol, date) for fast per-day lookups.
"""

from datetime import date, datetime
from decimal import Decimal

from sqlalchemy import (
    Date,
    DateTime,
    Enum,
    Index,
    Integer,
    Numeric,
    String,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base
from app.strategies.gerchik.levels import LevelType
from app.strategies.gerchik.energy import EnergyContext


class GerchikLevel(Base):
    """One precomputed level for a (symbol, date)."""

    __tablename__ = "gerchik_levels"
    __table_args__ = (Index("ix_gerchik_levels_symbol_date", "symbol", "date"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    symbol: Mapped[str] = mapped_column(String(20), nullable=False)
    date: Mapped[date] = mapped_column(Date, nullable=False)

    level_price: Mapped[Decimal] = mapped_column(Numeric(12, 4), nullable=False)
    level_type: Mapped[str] = mapped_column(
        Enum(
            LevelType,
            native_enum=False,
            length=32,
            values_callable=lambda x: [e.value for e in x],
        ),
        nullable=False,
    )
    total_score: Mapped[int] = mapped_column(Integer, nullable=False)

    trend: Mapped[str] = mapped_column(String(10), nullable=False)  # UP/DOWN/NEUTRAL
    energy: Mapped[str] = mapped_column(
        Enum(
            EnergyContext,
            native_enum=False,
            length=20,
            values_callable=lambda x: [e.value for e in x],
        ),
        nullable=False,
    )

    path_ratio: Mapped[Decimal] = mapped_column(Numeric(12, 4), nullable=False)
    atr: Mapped[Decimal] = mapped_column(Numeric(12, 4), nullable=False)
    prev_close: Mapped[Decimal] = mapped_column(Numeric(12, 4), nullable=False)

    created_at: Mapped[datetime] = mapped_column(
        DateTime,
        server_default=func.now(),
        nullable=False,
    )
