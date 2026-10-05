"""Data loading service: fetch candles from a provider and persist them."""

import logging
import pandas as pd

from datetime import date

from sqlalchemy.dialects.sqlite import insert as sqlite_insert

from app.data_providers.base import MarketDataProvider
from app.data_providers.moex_iss.models import Candle as CandleDTO
from app.db.session import SessionLocal
from app.models.candle import Candle as CandleORM
import time
from dataclasses import dataclass


@dataclass
class LoadReport:
    """Result of a single load operation."""

    fetched: int
    inserted: int
    duplicates_skipped: int
    duration_seconds: float


logger = logging.getLogger(__name__)

# SQLite limit: ~999 variables per INSERT. 9 columns x 100 rows = 900.
BATCH_SIZE = 100

# Timeframes MOEX ISS supports natively. Everything else is resampled
# from 1-minute data.
MOEX_NATIVE_TIMEFRAMES = {1, 10, 60, 24}

# Target timeframe (minutes) -> pandas offset alias.
RESAMPLE_RULES: dict[int, str] = {
    5: "5min",
    30: "30min",
    120: "120min",
    240: "240min",
}


def _dto_to_orm(dto: CandleDTO) -> dict:
    """Convert a Pydantic Candle DTO into a dict for SQLAlchemy insert."""
    return {
        "symbol": dto.ticker,
        "timeframe": dto.timeframe,
        "timestamp": dto.begin,
        "open": dto.open,
        "high": dto.high,
        "low": dto.low,
        "close": dto.close,
        "value": dto.value,
        "volume": dto.volume,
    }


def _resample_dtos(
    dtos: list[CandleDTO],
    target_tf: int,
) -> list[CandleDTO]:
    """Resample a list of 1-minute CandleDTOs into a coarser timeframe.

    Uses pandas resample. Empty bins (weekends, outside trading hours)
    are dropped via dropna on `open`.
    """
    if not dtos:
        return []

    rule = RESAMPLE_RULES[target_tf]

    # Build a DataFrame with datetime index.
    df = (
        pd.DataFrame(
            {
                "begin": [d.begin for d in dtos],
                "open": [d.open for d in dtos],
                "high": [d.high for d in dtos],
                "low": [d.low for d in dtos],
                "close": [d.close for d in dtos],
                "volume": [d.volume for d in dtos],
                "value": [d.value for d in dtos],
            }
        )
        .set_index("begin")
        .sort_index()
    )

    # Aggregate.
    resampled = (
        df.resample(rule, label="left", closed="left")
        .agg(
            {
                "open": "first",
                "high": "max",
                "low": "min",
                "close": "last",
                "volume": "sum",
                "value": "sum",
            }
        )
        .dropna(subset=["open"])
    )

    ticker = dtos[0].ticker
    result: list[CandleDTO] = []
    step = pd.Timedelta(minutes=target_tf)
    one_sec = pd.Timedelta(seconds=1)

    for begin, row in resampled.iterrows():
        begin_dt = begin.to_pydatetime()
        end_dt = (begin + step - one_sec).to_pydatetime()
        result.append(
            CandleDTO(
                ticker=ticker,
                timeframe=target_tf,
                begin=begin_dt,
                end=end_dt,
                open=float(row["open"]),
                high=float(row["high"]),
                low=float(row["low"]),
                close=float(row["close"]),
                volume=int(row["volume"]),
                value=float(row["value"] or 0.0),
            )
        )

    return result


class DataLoader:
    """Fetch candles from a provider and persist them to SQLite."""

    def __init__(self, provider: MarketDataProvider) -> None:
        self._provider = provider

    async def load_ticker(
        self,
        ticker: str,
        timeframe: int,
        start: date,
        end: date,
    ) -> int:
        """Fetch candles for one ticker and insert them in batches."""
        logger.info("%s: fetching tf=%s from %s to %s", ticker, timeframe, start, end)

        dtos = await self._provider.fetch_candles(ticker, timeframe, start, end)

        if not dtos:
            logger.warning("%s: empty response from provider", ticker)
            return 0

        rows = [_dto_to_orm(dto) for dto in dtos]
        sent = 0

        with SessionLocal() as db:
            for i in range(0, len(rows), BATCH_SIZE):
                batch = rows[i : i + BATCH_SIZE]
                stmt = sqlite_insert(CandleORM).values(batch)
                stmt = stmt.on_conflict_do_nothing(
                    index_elements=["symbol", "timeframe", "timestamp"]
                )
                db.execute(stmt)
                sent += len(batch)
            db.commit()

        logger.info("%s: fetched %s candles, sent %s to DB", ticker, len(dtos), sent)
        return sent

    async def load_many(
        self,
        tickers: list[str],
        timeframe: int,
        start: date,
        end: date,
    ) -> dict[str, int]:
        """Load multiple tickers sequentially. Errors caught per ticker."""
        results: dict[str, int] = {}

        for ticker in tickers:
            try:
                results[ticker] = await self.load_ticker(ticker, timeframe, start, end)
            except Exception as exc:
                logger.error("%s: failed — %s: %s", ticker, type(exc).__name__, exc)
                results[ticker] = 0

        return results

    async def load_and_report(
        self,
        symbol: str,
        timeframe: int,
        start: date,
        end: date,
    ) -> LoadReport:
        """Fetch candles and insert them, returning a detailed report.

        Idempotent: re-running with the same period will report
        inserted=0 and duplicates_skipped=N.
        """
        t0 = time.perf_counter()
        logger.info("Loading %s %s from %s to %s", symbol, timeframe, start, end)

        # Decide whether we fetch natively or fetch 1m and resample.
        if timeframe in MOEX_NATIVE_TIMEFRAMES:
            fetch_tf = timeframe
        else:
            fetch_tf = 1  # fetch 1-minute, resample below

        dtos = await self._provider.fetch_candles(symbol, fetch_tf, start, end)

        if fetch_tf != timeframe:
            logger.info("Resampling %s from 1m to %sm", symbol, timeframe)
            dtos = _resample_dtos(dtos, target_tf=timeframe)
        fetched = len(dtos)

        if fetched == 0:
            logger.warning("%s %s: empty response from provider", symbol, timeframe)
            return LoadReport(
                fetched=0,
                inserted=0,
                duplicates_skipped=0,
                duration_seconds=time.perf_counter() - t0,
            )

        rows = [_dto_to_orm(dto) for dto in dtos]
        inserted = 0
        with SessionLocal() as db:
            for i in range(0, len(rows), BATCH_SIZE):
                batch = rows[i : i + BATCH_SIZE]
                stmt = sqlite_insert(CandleORM).values(batch)
                stmt = stmt.on_conflict_do_nothing(
                    index_elements=["symbol", "timeframe", "timestamp"]
                )
                result = db.execute(stmt)
                inserted += result.rowcount or 0
            db.commit()

        duration = time.perf_counter() - t0
        skipped = fetched - inserted
        logger.info(
            "Loaded %s %s: fetched=%s, inserted=%s, duration=%.2fs",
            symbol,
            timeframe,
            fetched,
            inserted,
            duration,
        )

        return LoadReport(
            fetched=fetched,
            inserted=inserted,
            duplicates_skipped=skipped,
            duration_seconds=duration,
        )
