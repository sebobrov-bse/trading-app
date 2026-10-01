"""Read candles from SQLite into a pandas DataFrame for backtesting."""

from datetime import datetime

import pandas as pd
from sqlalchemy import select

from app.db.session import SessionLocal
from app.models.candle import Candle


class CandleRepository:
    """Read-only access to the candles table."""

    def get_dataframe(
        self,
        symbol: str,
        timeframe: int,
        start: datetime | None = None,
        end: datetime | None = None,
    ) -> pd.DataFrame:
        """Return candles as a DataFrame indexed by timestamp.

        Columns: open, high, low, close, volume.
        Numeric columns cast to float — Backtrader expects floats,
        SQLite returns Decimal for Numeric columns.
        """
        with SessionLocal() as db:
            stmt = select(Candle).where(
                Candle.symbol == symbol,
                Candle.timeframe == timeframe,
            )
            if start is not None:
                stmt = stmt.where(Candle.timestamp >= start)
            if end is not None:
                stmt = stmt.where(Candle.timestamp <= end)

            stmt = stmt.order_by(Candle.timestamp.asc())
            rows = db.execute(stmt).scalars().all()

        if not rows:
            return pd.DataFrame(columns=["open", "high", "low", "close", "volume"])

        df = pd.DataFrame(
            {
                "datetime": [r.timestamp for r in rows],
                "open": [float(r.open) for r in rows],
                "high": [float(r.high) for r in rows],
                "low": [float(r.low) for r in rows],
                "close": [float(r.close) for r in rows],
                "volume": [int(r.volume) for r in rows],
            }
        )
        df.set_index("datetime", inplace=True)
        df.index = pd.to_datetime(df.index)
        return df

    def get_summary(
        self,
        symbol: str | None = None,
        timeframe: int | None = None,
    ) -> list[dict]:
        """Return a summary per (symbol, timeframe) using SQL aggregates.

        Using COUNT/MIN/MAX in SQL is much faster than loading all rows
        and computing in Python — especially on large tables.
        """
        from sqlalchemy import func

        with SessionLocal() as db:
            stmt = (
                select(
                    Candle.symbol,
                    Candle.timeframe,
                    func.count(Candle.id).label("candles_count"),
                    func.min(Candle.timestamp).label("first_timestamp"),
                    func.max(Candle.timestamp).label("last_timestamp"),
                )
                .group_by(Candle.symbol, Candle.timeframe)
                .order_by(Candle.symbol, Candle.timeframe)
            )
            if symbol:
                stmt = stmt.where(Candle.symbol == symbol)
            if timeframe:
                stmt = stmt.where(Candle.timeframe == timeframe)

            rows = db.execute(stmt).all()

        return [
            {
                "symbol": r.symbol,
                "timeframe": r.timeframe,
                "candles_count": r.candles_count,
                "first_timestamp": r.first_timestamp,
                "last_timestamp": r.last_timestamp,
            }
            for r in rows
        ]

    def delete_candles(self, symbol: str, timeframe: int) -> int:
        """Delete all candles for a (symbol, timeframe). Returns count."""
        from sqlalchemy import delete as sa_delete

        with SessionLocal() as db:
            stmt = sa_delete(Candle).where(
                Candle.symbol == symbol,
                Candle.timeframe == timeframe,
            )
            result = db.execute(stmt)
            db.commit()
            return result.rowcount or 0
