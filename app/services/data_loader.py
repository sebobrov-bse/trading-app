"""Data loading service: fetch candles from a provider and persist them."""

import logging
import time
from dataclasses import dataclass
from datetime import date, datetime

import pandas as pd
from sqlalchemy import select
from sqlalchemy.dialects.sqlite import insert as sqlite_insert

from app.data_providers.base import MarketDataProvider
from app.data_providers.moex_iss.futures import FuturesContract
from app.data_providers.moex_iss.models import Candle as CandleDTO
from app.db.session import SessionLocal
from app.models.candle import Candle as CandleORM
from app.models.instrument_spec import InstrumentSpec

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


@dataclass
class LoadReport:
    """Result of a single load operation."""

    fetched: int
    inserted: int
    duplicates_skipped: int
    duration_seconds: float


def _dto_to_orm(dto: CandleDTO) -> dict:
    """Convert a Pydantic Candle DTO into a dict for SQLAlchemy insert."""
    return {
        "symbol": dto.ticker,
        "asset_type": dto.asset_type,
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

    df = (
        pd.DataFrame(
            {
                "begin": [d.begin for d in dtos],
                "open": [float(d.open) for d in dtos],
                "high": [float(d.high) for d in dtos],
                "low": [float(d.low) for d in dtos],
                "close": [float(d.close) for d in dtos],
                "volume": [int(d.volume) for d in dtos],
                "value": [float(d.value) for d in dtos],
            }
        )
        .set_index("begin")
        .sort_index()
    )

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
    asset_type = dtos[0].asset_type
    step = pd.Timedelta(minutes=target_tf)
    one_sec = pd.Timedelta(seconds=1)

    result: list[CandleDTO] = []
    for begin, row in resampled.iterrows():
        begin_dt = begin.to_pydatetime()
        end_dt = (begin + step - one_sec).to_pydatetime()
        result.append(
            CandleDTO(
                ticker=ticker,
                asset_type=asset_type,
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
    """Fetch candles from a provider and persist them to SQLite.

    Idempotent: re-running with the same (ticker, timeframe, period)
    skips existing candles via ON CONFLICT DO NOTHING.
    """

    def __init__(self, provider: MarketDataProvider) -> None:
        self._provider = provider

    async def load_ticker(
        self,
        ticker: str,
        timeframe: int,
        start: date,
        end: date,
    ) -> int:
        """Fetch candles for one ticker and insert them in batches.

        Returns rows *sent* to DB.
        """
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
                    index_elements=["symbol", "asset_type", "timeframe", "timestamp"]
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

        For non-native timeframes (5, 30, 120, 240) fetches 1m and resamples.
        Idempotent: re-running with the same period reports inserted=0.
        """
        t0 = time.perf_counter()
        logger.info("Loading %s %s from %s to %s", symbol, timeframe, start, end)

        if timeframe in MOEX_NATIVE_TIMEFRAMES:
            fetch_tf = timeframe
        else:
            fetch_tf = 1

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
                    index_elements=["symbol", "asset_type", "timeframe", "timestamp"]
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

    async def load_futures(
        self,
        secid: str,
        timeframe: int,
        start: date,
        end: date,
    ) -> LoadReport:
        """Fetch futures candles and insert them into the DB.

        `secid` is the MOEX internal code (e.g. SRH7), NOT shortname.
        Saves with asset_type='future'.
        """
        t0 = time.perf_counter()
        logger.info("Loading futures %s %s from %s to %s", secid, timeframe, start, end)

        if timeframe in MOEX_NATIVE_TIMEFRAMES:
            fetch_tf = timeframe
        else:
            fetch_tf = 1

        dtos = await self._provider.fetch_futures_candles(secid, fetch_tf, start, end)

        if fetch_tf != timeframe:
            logger.info("Resampling futures %s from 1m to %sm", secid, timeframe)
            dtos = _resample_dtos(dtos, target_tf=timeframe)

        fetched = len(dtos)
        if fetched == 0:
            logger.warning("Futures %s %s: empty response from provider", secid, timeframe)
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
                    index_elements=["symbol", "asset_type", "timeframe", "timestamp"]
                )
                result = db.execute(stmt)
                inserted += result.rowcount or 0
            db.commit()

        duration = time.perf_counter() - t0
        skipped = fetched - inserted
        logger.info(
            "Loaded futures %s %s: fetched=%s, inserted=%s, duration=%.2fs",
            secid,
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

    def save_spec(self, contract: FuturesContract) -> None:
        """Upsert an InstrumentSpec for a futures contract.

        Uses the unique (symbol, asset_type) constraint: if the spec
        already exists, its fields are updated.
        """
        with SessionLocal() as db:
            existing = db.execute(
                select(InstrumentSpec).where(
                    InstrumentSpec.symbol == contract.secid,
                    InstrumentSpec.asset_type == "future",
                )
            ).scalar_one_or_none()

            expiration_dt = datetime.combine(contract.expiration_date, datetime.min.time())

            if existing is None:
                db.add(
                    InstrumentSpec(
                        symbol=contract.secid,
                        asset_type="future",
                        display_name=contract.shortname,
                        contract_multiplier=contract.contract_multiplier,
                        tick_size=contract.tick_size,
                        tick_value=contract.tick_value,
                        expiration_date=expiration_dt,
                        base_asset=contract.base_asset,
                        is_active=True,
                    )
                )
            else:
                existing.display_name = contract.shortname
                existing.contract_multiplier = contract.contract_multiplier
                existing.tick_size = contract.tick_size
                existing.tick_value = contract.tick_value
                existing.expiration_date = expiration_dt
                existing.base_asset = contract.base_asset
                existing.is_active = True

            db.commit()

    def save_dataframe(
        self,
        df: "pd.DataFrame",
        symbol: str,
        asset_type: str,
        timeframe: int,
        replace: bool = False,
    ) -> LoadReport:
        """Upsert a DataFrame (from ContinuousSeriesBuilder) into candles.

        Expected columns: timestamp, open, high, low, close, volume.
        `symbol` overrides the per-row secid — the series is saved
        under a single symbol like SBERF.

        If `replace=True`, first deletes all existing rows with the same
        (symbol, asset_type, timeframe) and then inserts. Use it for
        continuous series, which are rebuilt atomically.
        """
        t0 = time.perf_counter()
        if df.empty:
            return LoadReport(
                fetched=0,
                inserted=0,
                duplicates_skipped=0,
                duration_seconds=0.0,
            )

        rows: list[dict] = []
        for _, r in df.iterrows():
            rows.append(
                {
                    "symbol": symbol,
                    "asset_type": asset_type,
                    "timeframe": timeframe,
                    "timestamp": r["timestamp"],
                    "open": r["open"],
                    "high": r["high"],
                    "low": r["low"],
                    "close": r["close"],
                    "volume": int(r["volume"]),
                    "value": None,
                }
            )

        from sqlalchemy import delete as sa_delete

        inserted = 0
        with SessionLocal() as db:
            if replace:
                del_result = db.execute(
                    sa_delete(CandleORM).where(
                        CandleORM.symbol == symbol,
                        CandleORM.asset_type == asset_type,
                        CandleORM.timeframe == timeframe,
                    )
                )
                logger.info(
                    "Replacing %s %s: deleted %s old rows.",
                    symbol,
                    asset_type,
                    del_result.rowcount,
                )

            for i in range(0, len(rows), BATCH_SIZE):
                batch = rows[i : i + BATCH_SIZE]
                stmt = sqlite_insert(CandleORM).values(batch)
                stmt = stmt.on_conflict_do_nothing(
                    index_elements=["symbol", "asset_type", "timeframe", "timestamp"]
                )
                result = db.execute(stmt)
                inserted += result.rowcount or 0
            db.commit()

        duration = time.perf_counter() - t0
        fetched = len(rows)
        logger.info(
            "Saved continuous %s %s: fetched=%s, inserted=%s, duration=%.2fs",
            symbol,
            timeframe,
            fetched,
            inserted,
            duration,
        )
        return LoadReport(
            fetched=fetched,
            inserted=inserted,
            duplicates_skipped=fetched - inserted,
            duration_seconds=duration,
        )
