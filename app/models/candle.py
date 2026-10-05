from datetime import datetime
from decimal import Decimal

from sqlalchemy import (
    BigInteger,
    DateTime,
    Index,
    Integer,
    Numeric,
    String,
    UniqueConstraint,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class Candle(Base):
    """OHLCV candle for stocks and futures.

    Unique (symbol, asset_type, timeframe, timestamp) prevents duplicates
    on repeated loads. Composite index speeds up range queries.
    """

    __tablename__ = "candles"
    __table_args__ = (
        UniqueConstraint(
            "symbol",
            "asset_type",
            "timeframe",
            "timestamp",
            name="uq_candle_symbol_asset_tf_ts",
        ),
        Index(
            "ix_candle_symbol_asset_tf_ts",
            "symbol",
            "asset_type",
            "timeframe",
            "timestamp",
        ),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    symbol: Mapped[str] = mapped_column(String(20), nullable=False, index=True)
    asset_type: Mapped[str] = mapped_column(
        String(10),
        nullable=False,
        default="stock",
        server_default="stock",
        index=True,
    )
    timeframe: Mapped[int] = mapped_column(Integer, nullable=False)
    timestamp: Mapped[datetime] = mapped_column(DateTime, nullable=False, index=True)

    open: Mapped[Decimal] = mapped_column(Numeric(12, 4), nullable=False)
    high: Mapped[Decimal] = mapped_column(Numeric(12, 4), nullable=False)
    low: Mapped[Decimal] = mapped_column(Numeric(12, 4), nullable=False)
    close: Mapped[Decimal] = mapped_column(Numeric(12, 4), nullable=False)
    volume: Mapped[int] = mapped_column(BigInteger, nullable=False)

    value: Mapped[Decimal | None] = mapped_column(Numeric(20, 2), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now(), nullable=False
    )

    def __repr__(self) -> str:
        return (
            f"<Candle {self.symbol} ({self.asset_type}) tf={self.timeframe} "
            f"{self.timestamp} close={self.close}>"
        )
