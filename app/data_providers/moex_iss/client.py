import asyncio
from datetime import date, datetime

import httpx

from app.data_providers.base import MarketDataProvider
from app.data_providers.moex_iss.models import Candle

BASE_URL = "https://iss.moex.com/iss"

# Supported timeframes (minutes per candle). Same values as MOEX intervals.
SUPPORTED_TIMEFRAMES = {1, 10, 60, 24, 7, 31}

# MOEX returns at most 500 candles per page.
PAGE_SIZE = 500

# Polite delay between paginated requests (seconds).
PAGE_DELAY = 0.2

# Retry policy for 429 / timeouts.
MAX_RETRIES = 3
INITIAL_BACKOFF = 0.5


class MoexIssProvider(MarketDataProvider):
    """MOEX ISS market data provider (async)."""

    def __init__(self, base_url: str = BASE_URL, timeout: float = 10.0) -> None:
        self._base_url = base_url.rstrip("/")
        self._timeout = timeout

    def _build_url(self, ticker: str) -> str:
        """Build the candles endpoint URL for a ticker."""
        return (
            f"{self._base_url}/engines/stock/markets/shares"
            f"/securities/{ticker}/candles.json"
        )

    async def _fetch_with_retry(
        self,
        client: httpx.AsyncClient,
        url: str,
        params: dict,
    ) -> dict:
        """Fetch JSON with retry on 429 and network timeouts.

        Raises httpx.HTTPStatusError on 4xx/5xx (except 429, which retries).
        """
        backoff = INITIAL_BACKOFF
        last_exc: Exception | None = None

        for attempt in range(MAX_RETRIES):
            try:
                response = await client.get(url, params=params)
                if response.status_code == 429:
                    await asyncio.sleep(backoff)
                    backoff *= 2
                    continue
                response.raise_for_status()
                return response.json()
            except httpx.TimeoutException as exc:
                last_exc = exc
                if attempt == MAX_RETRIES - 1:
                    raise
                await asyncio.sleep(backoff)
                backoff *= 2

        if last_exc is not None:
            raise last_exc
        raise RuntimeError("MOEX ISS: max retries exceeded")

    def _parse_response(
        self,
        payload: dict,
        ticker: str,
        timeframe: int,
    ) -> list[Candle]:
        """Convert MOEX candles block into a list of Candle objects."""
        block = payload.get("candles") or {}
        columns = block.get("columns") or []
        data = block.get("data") or []

        if not columns or not data:
            return []

        candles: list[Candle] = []
        for row in data:
            record = dict(zip(columns, row))
            candles.append(
                Candle(
                    ticker=ticker,
                    timeframe=timeframe,
                    begin=datetime.strptime(record["begin"], "%Y-%m-%d %H:%M:%S"),
                    end=datetime.strptime(record["end"], "%Y-%m-%d %H:%M:%S"),
                    open=float(record["open"]),
                    close=float(record["close"]),
                    high=float(record["high"]),
                    low=float(record["low"]),
                    value=float(record["value"]),
                    volume=int(record["volume"]),
                )
            )
        return candles

    async def fetch_candles(
        self,
        ticker: str,
        timeframe: int,
        start: date,
        end: date,
    ) -> list[Candle]:
        """Fetch candles with pagination.

        Loops with increasing `start` offset until MOEX returns an empty
        page or a partial page (< PAGE_SIZE rows).
        """
        if timeframe not in SUPPORTED_TIMEFRAMES:
            raise ValueError(
                f"Unsupported timeframe: {timeframe}. "
                f"Supported: {sorted(SUPPORTED_TIMEFRAMES)}"
            )

        url = self._build_url(ticker)
        all_candles: list[Candle] = []
        offset = 0

        async with httpx.AsyncClient(timeout=self._timeout) as client:
            while True:
                params = {
                    "from": start.isoformat(),
                    "till": end.isoformat(),
                    "interval": timeframe,
                    "start": offset,
                    "iss.meta": "off",
                }

                payload = await self._fetch_with_retry(client, url, params)
                page = self._parse_response(payload, ticker, timeframe)

                if not page:
                    break

                all_candles.extend(page)

                # Partial page means we've reached the end of the range.
                if len(page) < PAGE_SIZE:
                    break

                offset += PAGE_SIZE
                await asyncio.sleep(PAGE_DELAY)

        return all_candles