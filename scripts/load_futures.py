"""CLI: load MOEX futures contracts and specs into SQLite.

Examples:
  # List active contracts
  python -m scripts.load_futures --list

  # Load all active SBRF contracts for a year
  python -m scripts.load_futures --base SBRF --start 2025-10-01 --end 2026-10-01

  # Load specific contracts by SECID
  python -m scripts.load_futures --secids SRH7,SRM7 --start 2025-10-01

  # Load specs only (multipliers, expiration dates)
  python -m scripts.load_futures --load-specs --base SBRF

  # Custom timeframe (resampled from 1m)
  python -m scripts.load_futures --base SBRF --timeframe 30 --start 2025-10-01
"""

import argparse
import asyncio
import logging
from datetime import date, datetime
from app.services.continuous import ContinuousSeriesBuilder

from app.data_providers.moex_iss.client import MoexIssProvider
from app.data_providers.moex_iss.futures import FuturesContract
from app.services.data_loader import DataLoader

logger = logging.getLogger("load_futures")

VALID_TIMEFRAMES = {1, 5, 10, 30, 60, 120, 240, 24}


def parse_date(value: str) -> date:
    try:
        return datetime.strptime(value, "%Y-%m-%d").date()
    except ValueError as exc:
        raise argparse.ArgumentTypeError(f"Invalid date '{value}'. Expected YYYY-MM-DD.") from exc


def parse_secids(value: str) -> list[str]:
    result = [x.strip().upper() for x in value.split(",") if x.strip()]
    if not result:
        raise argparse.ArgumentTypeError("No SECIDs provided.")
    return result


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="load_futures",
        description="Load MOEX futures contracts and specs into SQLite.",
    )
    parser.add_argument(
        "--continuous",
        type=str,
        help="Build a continuous series for BASE (e.g. SBER → SBERF).",
    )
    parser.add_argument(
        "--continuous-symbol",
        type=str,
        help="Output symbol for the continuous series (default: <BASE>F).",
    )
    parser.add_argument(
        "--method",
        choices=["concat", "ratio"],
        default="ratio",
        help="Concatenation method for continuous series (default: ratio).",
    )
    parser.add_argument(
        "--roll-offset",
        type=int,
        default=5,
        help="Roll to next contract N days before expiration (default: 5).",
    )
    parser.add_argument(
        "--list",
        action="store_true",
        help="List active futures contracts and exit.",
    )
    parser.add_argument(
        "--base",
        type=str,
        help="Base asset code (SBRF, GAZR, LKOH, ...) — load all active.",
    )
    parser.add_argument(
        "--secids",
        type=parse_secids,
        help="Comma-separated SECIDs (e.g. SRH7,SRM7).",
    )
    parser.add_argument(
        "--timeframe",
        type=int,
        default=24,
        choices=sorted(VALID_TIMEFRAMES),
        help="Timeframe in minutes (default: 24).",
    )
    parser.add_argument(
        "--start",
        type=parse_date,
        help="Start date (YYYY-MM-DD).",
    )
    parser.add_argument(
        "--end",
        type=parse_date,
        default=date.today(),
        help="End date (YYYY-MM-DD, default: today).",
    )
    parser.add_argument(
        "--load-specs",
        action="store_true",
        help="Also save contract specifications (multiplier, expiration).",
    )
    parser.add_argument(
        "--log-level",
        default="INFO",
        choices=["DEBUG", "INFO", "WARNING", "ERROR"],
    )
    return parser


def pick_contracts(
    all_contracts: list[FuturesContract],
    base: str | None,
    secids: list[str] | None,
) -> list[FuturesContract]:
    """Filter active contracts by base code or explicit SECID list."""
    if secids:
        # Explicit list: match by SECID.
        lookup = {c.secid: c for c in all_contracts}
        result = [lookup[s] for s in secids if s in lookup]
        missing = [s for s in secids if s not in lookup]
        if missing:
            logger.warning("SECIDs not found: %s", missing)
        return result

    if base:
        base_upper = base.upper()
        return [c for c in all_contracts if c.asset_code == base_upper]

    return []


async def run_continuous(args: argparse.Namespace) -> int:
    """Build a continuous series and save it to candles."""
    base_asset = args.continuous.upper()
    out_symbol = (args.continuous_symbol or f"{base_asset}F").upper()

    if args.start is None:
        logger.error("--start is required for --continuous.")
        return 1

    logger.info(
        "Building continuous series for %s -> %s (method=%s, roll=%sd)",
        base_asset,
        out_symbol,
        args.method,
        args.roll_offset,
    )

    builder = ContinuousSeriesBuilder(
        base_asset=base_asset,
        roll_offset_days=args.roll_offset,
    )
    df = builder.build(
        timeframe=args.timeframe,
        start=args.start,
        end=args.end,
        method=args.method,
    )

    logger.info("Built %s rows, %s rolls.", len(df), len(builder.roll_events()))
    for r in builder.roll_events():
        logger.info(
            "  %s: %s -> %s (ratio=%.4f)",
            r.date,
            r.old_secid,
            r.new_secid,
            r.ratio,
        )

    provider = MoexIssProvider()
    loader = DataLoader(provider)
    report = loader.save_dataframe(
        df=df,
        symbol=out_symbol,
        asset_type="continuous",
        timeframe=args.timeframe,
        replace=True,
    )
    logger.info(
        "Saved %s: fetched=%s, inserted=%s, skipped=%s, duration=%.2fs",
        out_symbol,
        report.fetched,
        report.inserted,
        report.duplicates_skipped,
        report.duration_seconds,
    )
    return 0


async def run(args: argparse.Namespace) -> int:
    if args.continuous:
        return await run_continuous(args)
    provider = MoexIssProvider()

    logger.info("Fetching list of active futures from MOEX ISS...")
    all_contracts = await provider.fetch_futures_list()
    logger.info("Found %s active contracts.", len(all_contracts))

    if args.list:
        print(f"{'SECID':<12} {'SHORTNAME':<20} {'BASE':<8} {'EXP':<12} {'MULT':<6} {'TICK':<8}")
        print("-" * 80)
        for c in all_contracts:
            print(
                f"{c.secid:<12} {c.shortname:<20} {c.base_asset:<8} "
                f"{c.expiration_date.isoformat():<12} "
                f"{c.contract_multiplier:<6} {c.tick_size:<8}"
            )
        return 0

    contracts = pick_contracts(all_contracts, args.base, args.secids)
    if not contracts:
        logger.error("No contracts matched. Use --base SBRF or --secids SRH7,...")
        return 1

    logger.info("Matched %s contracts.", len(contracts))

    loader = DataLoader(provider)

    # 1. Save specs (optional but recommended before loading candles).
    if args.load_specs:
        for c in contracts:
            loader.save_spec(c)
        logger.info("Saved %s instrument specs.", len(contracts))

    # 2. Load candles (requires --start).
    if args.start is None:
        if args.load_specs:
            return 0  # spec-only run
        logger.error("--start is required when loading candles.")
        return 1

    total_inserted = 0
    for c in contracts:
        try:
            report = await loader.load_futures(
                secid=c.secid,
                timeframe=args.timeframe,
                start=args.start,
                end=args.end,
            )
            logger.info(
                "  %s (%s): fetched=%s, inserted=%s, skipped=%s",
                c.secid,
                c.shortname,
                report.fetched,
                report.inserted,
                report.duplicates_skipped,
            )
            total_inserted += report.inserted
        except Exception as exc:
            logger.error("%s: failed — %s: %s", c.secid, type(exc).__name__, exc)

    logger.info("Done. Total inserted: %s rows.", total_inserted)
    return 0


def main() -> None:
    parser = build_parser()
    args = parser.parse_args()

    logging.basicConfig(
        level=args.log_level,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )

    if args.start and args.start > args.end:
        parser.error(f"--start ({args.start}) must be <= --end ({args.end})")

    exit_code = asyncio.run(run(args))
    raise SystemExit(exit_code)


if __name__ == "__main__":
    main()
