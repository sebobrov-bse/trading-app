"""One point on the equity curve of a backtest run."""

from datetime import datetime
from decimal import Decimal

from sqlalchemy import DateTime, ForeignKey, Index, Integer, Numeric
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base


class BacktestEquity(Base):
    """One equity point (timestamp + portfolio value)."""

    __tablename__ = "backtest_equity"
    __table_args__ = (
        Index("ix_backtest_equity_backtest_ts", "backtest_id", "timestamp"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    backtest_id: Mapped[int] = mapped_column(
        ForeignKey("backtests.id", ondelete="CASCADE"), nullable=False
    )
    timestamp: Mapped[datetime] = mapped_column(DateTime, nullable=False)
    value: Mapped[Decimal] = mapped_column(Numeric(20, 2), nullable=False)

    backtest: Mapped["Backtest"] = relationship(back_populates="equity")