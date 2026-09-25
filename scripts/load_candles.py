"""Load candles from MOEX ISS into SQLite."""

from datetime import datetime, timedelta

from sqlalchemy.dialects.sqlite import insert as sqlite_insert

from app.db.session import SessionLocal
from app.models.candle import Candle
from scripts.test_moex import fetch_candles


# MOEX ISS returns timestamps in Moscow time (UTC+3).
MSK_OFFSET = timedelta(hours=3)


def parse_timestamp(value: str) -> datetime:
    """Parse MOEX 'YYYY-MM-DD HH:MM:SS' (MSK) into UTC datetime."""
    naive_msk = datetime.strptime(value, "%Y-%m-%d %H:%M:%S")
    return naive_msk - MSK_OFFSET


def load_candles(secid: str, timeframe: int, days: int) -> int:
    """Fetch candles from MOEX and upsert into DB. Returns row count."""
    raw = fetch_candles(secid, interval=timeframe, days=days)

    if not raw:
        print(f"No candles returned for {secid} tf={timeframe}")
        return 0

    rows = [
        {
            "symbol": secid,
            "timeframe": timeframe,
            "timestamp": parse_timestamp(c["begin"]),
            "open": c["open"],
            "high": c["high"],
            "low": c["low"],
            "close": c["close"],
            "value": c["value"],
            "volume": int(c["volume"]),
        }
        for c in raw
    ]

    with SessionLocal() as db:
        stmt = sqlite_insert(Candle).values(rows)
        stmt = stmt.on_conflict_do_nothing(
            index_elements=["symbol", "timeframe", "timestamp"]
        )
        db.execute(stmt)
        db.commit()

    return len(rows)


def main() -> None:
    """Entry point."""
    secid = "SBER"
    timeframe = 24
    days = 90

    print(f"Loading {secid} tf={timeframe} for {days} days...")
    count = load_candles(secid, timeframe, days)
    print(f"Processed {count} candles (duplicates skipped).")


if __name__ == "__main__":
    main()