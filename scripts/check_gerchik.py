"""CLI to exercise precompute_gerchik on selected dates.

Usage:
    python -m scripts.check_gerchik --symbol SBER \
        --start 2024-01-01 --end 2024-12-31 \
        --dates 2024-06-03,2024-06-10,2024-06-14,2024-06-21,2024-06-28 \
        --save

Prints a one-line summary per requested date, and (with --save)
writes the level rows to the gerchik_levels table.
"""

import argparse
import logging
from datetime import date, datetime

from app.db.session import SessionLocal
from app.strategies.gerchik.precompute import (
    precompute_gerchik,
    save_to_db,
)


def parse_date(value: str) -> date:
    try:
        return datetime.strptime(value, "%Y-%m-%d").date()
    except ValueError as exc:
        raise argparse.ArgumentTypeError(f"Invalid date '{value}'. Expected YYYY-MM-DD.") from exc


def parse_date_list(value: str) -> list[date]:
    return [parse_date(x.strip()) for x in value.split(",") if x.strip()]


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="check_gerchik",
        description="Gerchik precompute smoke test on selected dates",
    )
    p.add_argument("--symbol", required=True)
    p.add_argument("--start", required=True, type=parse_date)
    p.add_argument("--end", required=True, type=parse_date)
    p.add_argument("--dates", required=True, type=parse_date_list)
    p.add_argument("--save", action="store_true", help="Write level rows to gerchik_levels")
    p.add_argument("--log-level", default="INFO", choices=["DEBUG", "INFO", "WARNING", "ERROR"])
    return p


def main() -> None:
    args = build_parser().parse_args()
    logging.basicConfig(
        level=args.log_level,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        datefmt="%H:%M:%S",
    )

    with SessionLocal() as db:
        days = precompute_gerchik(db, args.symbol, args.start, args.end)

        if not days:
            print(f"No precomputed days for {args.symbol} {args.start}..{args.end}")
            return

        print(f"Precomputed {len(days)} days for {args.symbol} {args.start}..{args.end}\n")

        # Filter to requested dates for the printed summary.
        target = set(args.dates)
        matched = [d for d in days if d.date in target]

        for d in matched:
            print(
                f"{d.date}: ATR={d.atr:.2f}  prev={d.prev_close:.2f}  "
                f"close={d.close:.2f}  path={d.path_ratio:+.2f}  "
                f"trend={d.trend:8}  levels={len(d.rows)}"
            )
            for r in d.rows[:7]:
                print(
                    f"    {r.level_price:8.2f}  {r.level_type.value:16}  "
                    f"score={r.total_score}  energy={r.energy.value}"
                )
            if len(d.rows) > 7:
                print(f"    ... and {len(d.rows) - 7} more")

        # Save only the requested dates.
        if args.save:
            to_save = matched if matched else days
            n = save_to_db(db, to_save)
            print(f"\nSaved {n} rows to gerchik_levels for {len(to_save)} days")


if __name__ == "__main__":
    main()
