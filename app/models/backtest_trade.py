"""One closed trade within a backtest run."""

from datetime import datetime
from decimal import Decimal

from sqlalchemy import DateTime, ForeignKey, Index, Integer, Numeric, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base


class BacktestTrade(Base):
    """One closed trade."""

    __tablename__ = "backtest_trades"
    __table_args__ = (Index("ix_backtest_trades_backtest_id", "backtest_id"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    backtest_id: Mapped[int] = mapped_column(
        ForeignKey("backtests.id", ondelete="CASCADE"), nullable=False
    )

    entry_time: Mapped[datetime] = mapped_column(DateTime, nullable=False)
    exit_time: Mapped[datetime] = mapped_column(DateTime, nullable=False)
    entry_price: Mapped[Decimal] = mapped_column(Numeric(18, 6), nullable=False)
    exit_price: Mapped[Decimal] = mapped_column(Numeric(18, 6), nullable=False)
    size: Mapped[Decimal] = mapped_column(Numeric(18, 6), nullable=False)
    bars_held: Mapped[int] = mapped_column(Integer, nullable=False)
    pnl: Mapped[Decimal] = mapped_column(Numeric(20, 2), nullable=False)
    pnl_net: Mapped[Decimal] = mapped_column(Numeric(20, 2), nullable=False)
    pnl_percent: Mapped[Decimal] = mapped_column(Numeric(12, 4), nullable=False)

    # Optional context (only gerchik_rejection populates these).
    # Nullable: existing trades (SMA/RSI/Levin) predate these columns.
    pattern: Mapped[str | None] = mapped_column(String(20), nullable=True)
    level_score: Mapped[int | None] = mapped_column(Integer, nullable=True)
    energy: Mapped[str | None] = mapped_column(String(20), nullable=True)
    path_ratio: Mapped[Decimal | None] = mapped_column(Numeric(12, 4), nullable=True)

    backtest: Mapped["Backtest"] = relationship(back_populates="trades")
