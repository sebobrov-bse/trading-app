"""Grid backtest runner for LevinSystem.

Iterates over tickers × timeframes × stop variants × hold days,
runs a backtest for each combination, persists results to DB.

Data prerequisites:
- 1m candles for each ticker (for level precomputation).
- Target-timeframe candles (15m/30m/60m).

Usage:
    python -m scripts.run_levin_grid \
        --tickers SBER,GAZP \
        --timeframes 30 \
        --stop-variants fixed,trailing_r \
        --hold-days 1,3 \
        --start 2026-07-01 --end 2026-10-01

    # Dry run: show combinations only
    python -m scripts.run_levin_grid ... --dry-run

    # Force re-run even if results exist
    python -m scripts.run_levin_grid ... --force
"""

import argparse
import logging
from datetime import date, datetime

from sqlalchemy import select

from app.db.session import SessionLocal
from app.models.backtest import Backtest
from app.schemas.backtest import BacktestRequest
from app.services.backtest_service import run_backtest

logger = logging.getLogger("levin_grid")


def parse_date(value: str) -> date:
    try:
        return datetime.strptime(value, "%Y-%m-%d").date()
    except ValueError as exc:
        raise argparse.ArgumentTypeError(f"Invalid date '{value}'. Expected YYYY-MM-DD.") from exc


def parse_list(value: str) -> list[str]:
    items = [x.strip() for x in value.split(",") if x.strip()]
    if not items:
        raise argparse.ArgumentTypeError("Empty list")
    return items


def parse_int_list(value: str) -> list[int]:
    try:
        return [int(x.strip()) for x in value.split(",") if x.strip()]
    except ValueError as exc:
        raise argparse.ArgumentTypeError(f"Invalid integer list '{value}'") from exc


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="run_levin_grid",
        description="Grid backtest for LevinSystem",
    )
    p.add_argument("--tickers", required=True, type=parse_list)
    p.add_argument("--timeframes", required=True, type=parse_int_list)
    p.add_argument(
        "--stop-variants",
        default="fixed,trailing_r,dynamic_minmax",
        type=parse_list,
    )
    p.add_argument("--hold-days", default="1,3,5", type=parse_int_list)
    p.add_argument("--start", required=True, type=parse_date)
    p.add_argument("--end", default=date.today(), type=parse_date)
    p.add_argument("--cash", type=float, default=100_000.0)
    p.add_argument("--commission", type=float, default=0.001)
    p.add_argument("--min-rr", type=float, default=3.0)
    p.add_argument(
        "--log-level",
        default="INFO",
        choices=["DEBUG", "INFO", "WARNING", "ERROR"],
    )
    p.add_argument("--dry-run", action="store_true")
    p.add_argument("--force", action="store_true")
    return p


def _has_data(symbol: str, timeframe: int, start: date, end: date) -> bool:
    """Check that there are at least 100 candles for (symbol, TF)."""
    from app.models.candle import Candle

    with SessionLocal() as db:
        stmt = (
            select(Candle.id)
            .where(
                Candle.symbol == symbol,
                Candle.timeframe == timeframe,
                Candle.timestamp >= datetime.combine(start, datetime.min.time()),
                Candle.timestamp <= datetime.combine(end, datetime.max.time()),
            )
            .limit(100)
        )
        return len(db.execute(stmt).scalars().all()) >= 100


def _already_run(
    symbol: str,
    timeframe: int,
    start: date,
    end: date,
    params: dict,
) -> bool:
    """Check if a backtest with same key exists."""
    with SessionLocal() as db:
        stmt = select(Backtest.id).where(
            Backtest.symbol == symbol,
            Backtest.timeframe == timeframe,
            Backtest.strategy == "levin",
            Backtest.start_date == datetime.combine(start, datetime.min.time()),
            Backtest.end_date == datetime.combine(end, datetime.min.time()),
        )
        for row in db.execute(stmt).scalars().all():
            # Check exact params match.
            existing = db.get(Backtest, row)
            if existing and existing.params == params:
                return True
    return False


def main() -> None:
    parser = build_parser()
    args = parser.parse_args()

    logging.basicConfig(
        level=args.log_level,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )

    if args.start > args.end:
        parser.error("--start must be <= --end")

    combos: list[dict] = []
    for ticker in args.tickers:
        for tf in args.timeframes:
            for sv in args.stop_variants:
                for hd in args.hold_days:
                    combos.append(
                        {
                            "ticker": ticker,
                            "timeframe": tf,
                            "stop_variant": sv,
                            "max_hold_days": hd,
                        }
                    )

    logger.info(
        "Grid: %s tickers × %s TFs × %s variants × %s hold = %s backtests",
        len(args.tickers),
        len(args.timeframes),
        len(args.stop_variants),
        len(args.hold_days),
        len(combos),
    )

    if args.dry_run:
        for c in combos:
            print(
                f"  {c['ticker']:6} TF={c['timeframe']:3} "
                f"stop={c['stop_variant']:16} hold={c['max_hold_days']}"
            )
        return

    results: list[dict] = []
    skipped_data = 0
    skipped_existing = 0
    failed = 0

    for idx, c in enumerate(combos, 1):
        ticker = c["ticker"]
        tf = c["timeframe"]
        sv = c["stop_variant"]
        hd = c["max_hold_days"]

        logger.info(
            "[%s/%s] %s TF=%s stop=%s hold=%s",
            idx,
            len(combos),
            ticker,
            tf,
            sv,
            hd,
        )

        # Check data.
        if not _has_data(ticker, 1, args.start, args.end):
            logger.warning("  skip: no 1m data for %s", ticker)
            skipped_data += 1
            continue
        if not _has_data(ticker, tf, args.start, args.end):
            logger.warning("  skip: no %sm data for %s", tf, ticker)
            skipped_data += 1
            continue

        params = {
            "stop_variant": sv,
            "max_hold_days": hd,
            "min_rr": args.min_rr,
        }

        if not args.force and _already_run(ticker, tf, args.start, args.end, params):
            logger.info("  skip: already in DB")
            skipped_existing += 1
            continue

        request = BacktestRequest(
            symbol=ticker,
            timeframe=tf,
            start=args.start,
            end=args.end,
            strategy="levin",
            params=params,
            cash=args.cash,
            commission=args.commission,
        )

        try:
            result = run_backtest(request)
            logger.info(
                "  OK: PnL=%.2f Sharpe=%.2f DD=%.2f%% trades=%s",
                result.pnl,
                result.sharpe,
                result.max_drawdown,
                result.trades,
            )
            results.append(
                {
                    "ticker": ticker,
                    "timeframe": tf,
                    "stop_variant": sv,
                    "max_hold_days": hd,
                    "pnl": result.pnl,
                    "sharpe": result.sharpe,
                    "max_dd": result.max_drawdown,
                    "trades": result.trades,
                    "id": result.id,
                }
            )
        except Exception as exc:
            logger.error("  FAIL: %s: %s", type(exc).__name__, exc)
            failed += 1

    # Summary.
    print()
    print("=" * 90)
    print(
        f"{'Ticker':<8} {'TF':>3} {'Stop':<16} {'Hold':>4} "
        f"{'PnL':>10} {'Sharpe':>8} {'MaxDD':>8} {'Trades':>6}"
    )
    print("-" * 90)
    for r in sorted(results, key=lambda x: x["sharpe"], reverse=True):
        print(
            f"{r['ticker']:<8} {r['timeframe']:>3} {r['stop_variant']:<16} "
            f"{r['max_hold_days']:>4} {r['pnl']:>10.2f} "
            f"{r['sharpe']:>8.2f} {r['max_dd']:>8.2f} {r['trades']:>6}"
        )
    print("-" * 90)
    print(
        f"Total: {len(results)} OK, {skipped_data} no-data, "
        f"{skipped_existing} already-in-DB, {failed} failed"
    )


if __name__ == "__main__":
    main()
