"""Test futures provider: list contracts and fetch candles."""

import asyncio
from datetime import date

from app.data_providers.moex_iss.client import MoexIssProvider


async def main() -> None:
    provider = MoexIssProvider()

    # 1. List active contracts
    contracts = await provider.fetch_futures_list()
    print(f"Total contracts: {len(contracts)}")
    print(
        f"{'SECID':<12} {'SHORTNAME':<20} {'BASE':<8} {'EXP':<12} "
        f"{'MULT':<6} {'TICK':<8} {'TICKVAL':<10}"
    )
    print("-" * 90)
    for c in contracts[:15]:
        print(
            f"{c.secid:<12} {c.shortname:<20} {c.base_asset:<8} "
            f"{c.expiration_date.isoformat():<12} {c.contract_multiplier:<6} "
            f"{c.tick_size:<8} {c.tick_value:<10}"
        )

    # 2. Fetch candles for SBRF-3.27 (SECID=SRH7)
    print()
    print("Fetching SBRF-3.27 (SRH7) candles...")
    candles = await provider.fetch_futures_candles(
        secid="SRH7",
        timeframe=24,
        start=date(2026, 10, 1),
        end=date(2026, 10, 5),
    )
    print(f"Candles: {len(candles)}")
    for c in candles[:3]:
        print(f"  {c.begin.isoformat()} | O={c.open} H={c.high} L={c.low} C={c.close} V={c.volume}")


if __name__ == "__main__":
    asyncio.run(main())
