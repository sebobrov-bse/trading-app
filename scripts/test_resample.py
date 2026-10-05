"""Test 1m -> 5m resampling on real MOEX data."""

from datetime import date

from app.services.data_loader import _resample_dtos
from app.data_providers.moex_iss.client import MoexIssProvider


async def main() -> None:
    provider = MoexIssProvider()

    print("Fetching 1m SBER for one day...")
    dtos_1m = await provider.fetch_candles(
        ticker="SBER",
        timeframe=1,
        start=date(2026, 10, 1),
        end=date(2026, 10, 1),
    )
    print(f"  1m candles: {len(dtos_1m)}")
    if dtos_1m:
        print(f"  First 1m: {dtos_1m[0].begin} -> {dtos_1m[0].end}")

    print("Resampling to 5m...")
    dtos_5m = _resample_dtos(dtos_1m, target_tf=5)
    print(f"  5m candles: {len(dtos_5m)}")
    for d in dtos_5m[:5]:
        print(
            f"  {d.begin.time()} -> {d.end.time()} | "
            f"O={d.open} H={d.high} L={d.low} C={d.close} V={d.volume}"
        )

    # Sanity check: sum of 1m volumes should equal sum of 5m volumes.
    v1 = sum(d.volume for d in dtos_1m)
    v5 = sum(d.volume for d in dtos_5m)
    print(f"Volume check: 1m={v1}, 5m={v5}, match={v1 == v5}")


if __name__ == "__main__":
    import asyncio

    asyncio.run(main())
