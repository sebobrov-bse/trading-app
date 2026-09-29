"""Backtest run: metadata and aggregated metrics."""

from datetime import datetime
from decimal import Decimal

from sqlalchemy import (
    JSON,
    DateTime,
    Index,
    Integer,
    Numeric,
    String,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base


class Backtest(Base):
    """One backtest run."""

    __tablename__ = "backtests"
    __table_args__ = (
        Index("ix_backtests_symbol_tf_created", "symbol", "timeframe", "created_at"),
        Index("ix_backtests_strategy_created", "strategy", "created_at"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    symbol: Mapped[str] = mapped_column(String(20), nullable=False)
    timeframe: Mapped[int] = mapped_column(Integer, nullable=False)
    start_date: Mapped[datetime] = mapped_column(DateTime, nullable=False)
    end_date: Mapped[datetime] = mapped_column(DateTime, nullable=False)
    strategy: Mapped[str] = mapped_column(String(50), nullable=False)
    params: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    cash: Mapped[Decimal] = mapped_column(Numeric(20, 2), nullable=False)
    commission: Mapped[Decimal] = mapped_column(Numeric(10, 6), nullable=False)

    bars: Mapped[int] = mapped_column(Integer, nullable=False)
    trades_count: Mapped[int] = mapped_column(Integer, nullable=False)
    final_value: Mapped[Decimal] = mapped_column(Numeric(20, 2), nullable=False)
    pnl: Mapped[Decimal] = mapped_column(Numeric(20, 2), nullable=False)
    pnl_percent: Mapped[Decimal] = mapped_column(Numeric(12, 4), nullable=False)

    cagr: Mapped[Decimal] = mapped_column(Numeric(12, 4), nullable=False)
    sharpe: Mapped[Decimal] = mapped_column(Numeric(12, 4), nullable=False)
    sortino: Mapped[Decimal] = mapped_column(Numeric(12, 4), nullable=False)
    calmar: Mapped[Decimal] = mapped_column(Numeric(12, 4), nullable=False)
    max_drawdown: Mapped[Decimal] = mapped_column(Numeric(12, 4), nullable=False)

    win_rate: Mapped[Decimal] = mapped_column(Numeric(12, 4), nullable=False)
    profit_factor: Mapped[Decimal] = mapped_column(Numeric(12, 4), nullable=False)
    avg_win: Mapped[Decimal] = mapped_column(Numeric(20, 2), nullable=False)
    avg_loss: Mapped[Decimal] = mapped_column(Numeric(20, 2), nullable=False)
    exposure: Mapped[Decimal] = mapped_column(Numeric(12, 4), nullable=False)

    created_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now(), nullable=False
    )

    trades: Mapped[list["BacktestTrade"]] = relationship(
        back_populates="backtest",
        cascade="all, delete-orphan",
    )
    equity: Mapped[list["BacktestEquity"]] = relationship(
        back_populates="backtest",
        cascade="all, delete-orphan",
    )

    def __repr__(self) -> str:
        return (
            f"<Backtest id={self.id} {self.symbol} tf={self.timeframe} "
            f"{self.strategy} pnl={self.pnl}>"
        )