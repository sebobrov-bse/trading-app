"""Test continuous series builder on real SBERF data."""

from datetime import date

from app.services.continuous import ContinuousSeriesBuilder


def main() -> None:
    # First run: realistic roll_offset (5 days). Should produce no rolls
    # because SRZ6 expires 2026-12-17 and data ends 2026-10-05.
    print("=" * 70)
    print("Run 1: roll_offset_days=5 (realistic)")
    print("=" * 70)

    builder1 = ContinuousSeriesBuilder(base_asset="SBER", roll_offset_days=5)
    df1 = builder1.build(
        timeframe=24,
        start=date(2025, 10, 1),
        end=date(2026, 10, 5),
        method="ratio",
    )
    print(f"Rows: {len(df1)}")
    print(f"Range: {df1['timestamp'].min()} .. {df1['timestamp'].max()}")
    print(f"Contracts used: {sorted(df1['secid'].unique())}")
    print(f"Rolls: {len(builder1.roll_events())}")
    print()

    # Second run: artificially large roll_offset to force rolls.
    print("=" * 70)
    print("Run 2: roll_offset_days=150 (forces rolls, for testing)")
    print("=" * 70)

    builder2 = ContinuousSeriesBuilder(base_asset="SBER", roll_offset_days=150)
    df2 = builder2.build(
        timeframe=24,
        start=date(2025, 10, 1),
        end=date(2026, 10, 5),
        method="ratio",
    )
    print(f"Rows: {len(df2)}")
    print(f"Contracts used: {sorted(df2['secid'].unique())}")
    print(f"Rolls: {len(builder2.roll_events())}")
    print()
    print("Roll events:")
    for r in builder2.roll_events():
        print(
            f"  {r.date}  {r.old_secid} -> {r.new_secid}  "
            f"(old_close={r.old_close:.2f}, new_open={r.new_open:.2f}, "
            f"ratio={r.ratio:.4f})"
        )
    print()
    print("First 3 rows:")
    print(df2.head(3).to_string())
    print()
    print("Last 3 rows:")
    print(df2.tail(3).to_string())


if __name__ == "__main__":
    main()
