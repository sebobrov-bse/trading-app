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
            return pd.DataFrame(
                columns=["open", "high", "low", "close", "volume"]
            )

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