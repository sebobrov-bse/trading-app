from datetime import datetime, timezone
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


def utcnow() -> datetime:
    """Return current UTC time as a timezone-aware datetime."""
    return datetime.now(timezone.utc)


class Candle(Base):
    """OHLCV candle from a market data provider."""

    __tablename__ = "candles"
    __table_args__ = (
        UniqueConstraint(
            "symbol", "timeframe", "timestamp", name="uq_candle_symbol_tf_ts"
        ),
        Index("ix_candle_symbol_tf_ts", "symbol", "timeframe", "timestamp"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    symbol: Mapped[str] = mapped_column(String(20), nullable=False, index=True)
    timeframe: Mapped[int] = mapped_column(Integer, nullable=False)
    timestamp: Mapped[datetime] = mapped_column(DateTime, nullable=False, index=True)

    open: Mapped[Decimal] = mapped_column(Numeric(12, 4), nullable=False)
    high: Mapped[Decimal] = mapped_column(Numeric(12, 4), nullable=False)
    low: Mapped[Decimal] = mapped_column(Numeric(12, 4), nullable=False)
    close: Mapped[Decimal] = mapped_column(Numeric(12, 4), nullable=False)
    volume: Mapped[int] = mapped_column(BigInteger, nullable=False)

    value: Mapped[Decimal | None] = mapped_column(Numeric(20, 2), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime,
        default=utcnow,
        server_default=func.now(),
        nullable=False,
    )

    def __repr__(self) -> str:
        return (
            f"<Candle {self.symbol} tf={self.timeframe} {self.timestamp} "
            f"close={self.close}>"
        )