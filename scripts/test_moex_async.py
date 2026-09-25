"""Test the async MOEX ISS loader."""

import asyncio
import time
from datetime import date, timedelta

from app.data_providers.moex_iss.client import MoexIssProvider


async def main() -> None:
    """Fetch SBER daily candles for the last 90 days."""
    provider = MoexIssProvider()

    end = date.today()
    start = end - timedelta(days=90)

    print(f"Fetching SBER tf=24 from {start} to {end}...")

    t0 = time.perf_counter()
    candles = await provider.fetch_candles(
        ticker="SBER",
        timeframe=24,
        start=start,
        end=end,
    )
    elapsed = time.perf_counter() - t0

    print(f"Fetched {len(candles)} candles in {elapsed:.2f}s")
    print("First 3 candles:")
    print("-" * 80)

    for c in candles[:3]:
        print(
            f"{c.begin} -> {c.end} | "
            f"O: {c.open:.2f} H: {c.high:.2f} "
            f"L: {c.low:.2f} C: {c.close:.2f} V: {c.volume}"
        )


if __name__ == "__main__":
    asyncio.run(main())
