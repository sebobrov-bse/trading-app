"""CLI: load historical candles from MOEX ISS into SQLite."""

import argparse
import asyncio
import logging
from datetime import date, datetime
from pathlib import Path

from app.data_providers.moex_iss.client import MoexIssProvider
from app.services.data_loader import DataLoader

logger = logging.getLogger("load_history")

VALID_TIMEFRAMES = {1, 10, 60, 24}


def parse_date(value: str) -> date:
    """Parse YYYY-MM-DD into a date. Raises ArgumentTypeError on bad input."""
    try:
        return datetime.strptime(value, "%Y-%m-%d").date()
    except ValueError as exc:
        raise argparse.ArgumentTypeError(
            f"Invalid date '{value}'. Expected YYYY-MM-DD."
        ) from exc


def parse_tickers(value: str) -> list[str]:
    """Parse tickers from 'SBER,GAZP' or '@path/to/tickers.txt'."""
    if value.startswith("@"):
        path = Path(value[1:])
        if not path.exists():
            raise argparse.ArgumentTypeError(f"Ticker file not found: {path}")
        tickers = [
            line.strip().upper()
            for line in path.read_text().splitlines()
            if line.strip()
        ]
    else:
        tickers = [t.strip().upper() for t in value.split(",") if t.strip()]

    if not tickers:
        raise argparse.ArgumentTypeError("No tickers provided.")

    return tickers


def build_parser() -> argparse.ArgumentParser:
    """Build the CLI argument parser."""
    parser = argparse.ArgumentParser(
        prog="load_history",
        description="Load historical candles from MOEX ISS into SQLite.",
    )
    parser.add_argument(
        "--tickers",
        required=True,
        type=parse_tickers,
        help="Comma-separated tickers (SBER,GAZP) or @path/to/tickers.txt",
    )
    parser.add_argument(
        "--timeframe",
        type=int,
        default=24,
        choices=sorted(VALID_TIMEFRAMES),
        help="Timeframe in minutes (default: 24)",
    )
    parser.add_argument(
        "--start",
        required=True,
        type=parse_date,
        help="Start date (YYYY-MM-DD)",
    )
    parser.add_argument(
        "--end",
        type=parse_date,
        default=date.today(),
        help="End date (YYYY-MM-DD, default: today)",
    )
    parser.add_argument(
        "--log-level",
        default="INFO",
        choices=["DEBUG", "INFO", "WARNING", "ERROR"],
        help="Logging level (default: INFO)",
    )
    return parser


async def run(args: argparse.Namespace) -> int:
    """Run the loader. Returns exit code (0 = success, 1 = some failures)."""
    provider = MoexIssProvider()
    loader = DataLoader(provider)

    logger.info(
        "Starting load: tickers=%s timeframe=%s period=%s..%s",
        args.tickers, args.timeframe, args.start, args.end,
    )

    results = await loader.load_many(
        tickers=args.tickers,
        timeframe=args.timeframe,
        start=args.start,
        end=args.end,
    )

    total = sum(results.values())
    failed = [t for t, c in results.items() if c == 0]

    logger.info(
        "Done. Processed %s tickers, %s rows sent to DB, failures: %s",
        len(results), total, len(failed),
    )
    for ticker, count in results.items():
        logger.info("  %s: %s candles", ticker, count)

    return 0 if not failed else 1


def main() -> None:
    """CLI entry point."""
    parser = build_parser()
    args = parser.parse_args()

    logging.basicConfig(
        level=args.log_level,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )

    if args.start > args.end:
        parser.error(f"--start ({args.start}) must be <= --end ({args.end})")

    exit_code = asyncio.run(run(args))
    raise SystemExit(exit_code)


if __name__ == "__main__":
    main()