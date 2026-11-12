"""Grid backtest runner for GerchikSystem.

Iterates over tickers × patterns × hold_days × min_path_ratios,
runs a backtest for each combination, persists to DB.

Data prerequisites:
- D1 candles for each ticker (for precompute).
- M1 candles for each day in [start, end] (for M1 timing).

Usage:
    python -m scripts.run_gerchik_grid \
        --tickers SBER \
        --start 2024-06-01 --end 2024-06-30 \
        --patterns bounce,breakout,limit_player \
        --hold-days 1,3,5 \
        --min-path-ratios 0.3,0.5,0.7

    # Dry run — just show combinations
    python -m scripts.run_gerchik_grid ... --dry-run

    # Force re-run even if same params exist
    python -m scripts.run_gerchik_grid ... --force
"""

import argparse
import logging
from datetime import date, datetime

from sqlalchemy import select

from app.db.session import SessionLocal
from app.models.backtest import Backtest
from app.schemas.backtest import BacktestRequest
from app.services.backtest_service import run_backtest

logger = logging.getLogger("gerchik_grid")


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
        raise argparse.ArgumentTypeError(f"Invalid int list '{value}'") from exc


def parse_float_list(value: str) -> list[float]:
    try:
        return [float(x.strip()) for x in value.split(",") if x.strip()]
    except ValueError as exc:
        raise argparse.ArgumentTypeError(f"Invalid float list '{value}'") from exc


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="run_gerchik_grid",
        description="Grid backtest for GerchikSystem",
    )
    p.add_argument("--tickers", required=True, type=parse_list)
    p.add_argument("--start", required=True, type=parse_date)
    p.add_argument("--end", required=True, type=parse_date)
    p.add_argument(
        "--patterns",
        default="bounce,breakout,limit_player",
        type=parse_list,
    )
    p.add_argument("--hold-days", default="1,3,5", type=parse_int_list)
    p.add_argument("--min-path-ratios", default="0.3,0.5,0.7", type=parse_float_list)
    p.add_argument("--cash", type=float, default=100_000.0)
    p.add_argument("--commission", type=float, default=0.001)
    p.add_argument(
        "--log-level",
        default="INFO",
        choices=["DEBUG", "INFO", "WARNING", "ERROR"],
    )
    p.add_argument("--dry-run", action="store_true")
    p.add_argument("--force", action="store_true")
    return p


def _has_data(
    symbol: str,
    timeframe: int,
    start: date,
    end: date,
    min_bars: int = 5,
) -> bool:
    """Check that there are at least `min_bars` candles for (symbol, TF)."""
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
            .limit(min_bars)
        )
        return len(db.execute(stmt).scalars().all()) >= min_bars


def _already_run(
    symbol: str,
    start: date,
    end: date,
    params: dict,
) -> bool:
    """Check if an equivalent backtest exists in DB."""
    with SessionLocal() as db:
        stmt = select(Backtest.id).where(
            Backtest.symbol == symbol,
            Backtest.timeframe == 24,
            Backtest.strategy == "gerchik",
            Backtest.start_date == datetime.combine(start, datetime.min.time()),
            Backtest.end_date == datetime.combine(end, datetime.min.time()),
        )
        for row in db.execute(stmt).scalars().all():
            existing = db.get(Backtest, row)
            if existing is None:
                continue
            # Compare only our keys, ignoring DB-side differences
            # (e.g. list vs tuple round-trip through JSON).
            ex = existing.params or {}
            if (
                ex.get("pattern") == params["pattern"]
                and int(ex.get("max_hold_days", -1)) == params["max_hold_days"]
                and abs(float(ex.get("min_path_ratio", -1)) - params["min_path_ratio"]) < 1e-9
            ):
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

    combos = []
    for ticker in args.tickers:
        for pattern in args.patterns:
            for hd in args.hold_days:
                for mpr in args.min_path_ratios:
                    combos.append(
                        {
                            "ticker": ticker,
                            "pattern": pattern,
                            "max_hold_days": hd,
                            "min_path_ratio": mpr,
                        }
                    )

    logger.info(
        "Grid: %s tickers × %s patterns × %s hold × %s path = %s backtests",
        len(args.tickers),
        len(args.patterns),
        len(args.hold_days),
        len(args.min_path_ratios),
        len(combos),
    )

    if args.dry_run:
        for c in combos:
            print(
                f"  {c['ticker']:6}  pattern={c['pattern']:14}  "
                f"hold={c['max_hold_days']:2}  "
                f"min_path={c['min_path_ratio']:.2f}"
            )
        return

    results: list[dict] = []
    skipped_data = 0
    skipped_existing = 0
    failed = 0

    for idx, c in enumerate(combos, 1):
        ticker = c["ticker"]
        pattern = c["pattern"]
        hd = c["max_hold_days"]
        mpr = c["min_path_ratio"]

        logger.info(
            "[%s/%s] %s pattern=%s hold=%s min_path=%.2f",
            idx,
            len(combos),
            ticker,
            pattern,
            hd,
            mpr,
        )

        if not _has_data(ticker, 24, args.start, args.end, min_bars=5):
            logger.warning("  skip: no D1 data for %s", ticker)
            skipped_data += 1
            continue
        if not _has_data(ticker, 1, args.start, args.end, min_bars=50):
            logger.warning("  skip: no M1 data for %s", ticker)
            skipped_data += 1
            continue

        params = {
            "pattern": pattern,
            "max_hold_days": hd,
            "min_path_ratio": mpr,
        }

        if not args.force and _already_run(ticker, args.start, args.end, params):
            logger.info("  skip: already in DB")
            skipped_existing += 1
            continue

        request = BacktestRequest(
            symbol=ticker,
            timeframe=24,
            start=args.start,
            end=args.end,
            strategy="gerchik",
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
                    "pattern": pattern,
                    "max_hold_days": hd,
                    "min_path_ratio": mpr,
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

    print()
    print("=" * 100)
    print(
        f"{'Ticker':<8} {'Pattern':<14} {'Hold':>4} {'Path':>5} "
        f"{'PnL':>10} {'Sharpe':>8} {'MaxDD':>8} {'Trades':>6}"
    )
    print("-" * 100)
    for r in sorted(results, key=lambda x: -x["sharpe"]):
        print(
            f"{r['ticker']:<8} {r['pattern']:<14} {r['max_hold_days']:>4} "
            f"{r['min_path_ratio']:>5.2f} {r['pnl']:>10.2f} "
            f"{r['sharpe']:>8.2f} {r['max_dd']:>8.2f} {r['trades']:>6}"
        )
    print("-" * 100)
    print(
        f"Total: {len(results)} OK, {skipped_data} no-data, "
        f"{skipped_existing} already-in-DB, {failed} failed"
    )


if __name__ == "__main__":
    main()
