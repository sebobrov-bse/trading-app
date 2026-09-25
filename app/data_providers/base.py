from abc import ABC, abstractmethod
from datetime import date

from app.data_providers.moex_iss.models import Candle


class MarketDataProvider(ABC):
    """Abstract interface for market data providers.

    Any provider (MOEX ISS, CCXT, T-Invest) must implement fetch_candles.
    Strategies depend on this interface, not on concrete providers.
    """

    @abstractmethod
    async def fetch_candles(
        self,
        ticker: str,
        timeframe: int,
        start: date,
        end: date,
    ) -> list[Candle]:
        """Fetch OHLCV candles for a ticker and date range.

        Args:
            ticker: Instrument symbol (SBER, BTC/USDT, ...).
            timeframe: Minutes per candle (1, 10, 60, 24, ...).
            start: Start date (inclusive).
            end: End date (inclusive).

        Returns:
            List of Candle objects, sorted by begin ascending.
        """
        ...