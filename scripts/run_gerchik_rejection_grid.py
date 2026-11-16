"""Grid backtest for GerchikRejection across config variants.

Runs GerchikRejection over (symbol, date_range) with different
strategy configs (timing mode, path threshold, allowed energies),
compares PnL/Sharpe/trades.

Usage:
    python -m scripts.run_gerchik_rejection_grid \
        --symbol SBER --start 2024-06-01 --end 2024-12-30

    # Custom variants file (JSON) — coming later.
"""

import argparse
import logging
from datetime import date, datetime

from sqlalchemy import select

from app.db.session import SessionLocal
from app.models.backtest import Backtest
from app.schemas.backtest import BacktestRequest
from app.services.backtest_service import run_backtest

logger = logging.getLogger("gerchik_rejection_grid")


VARIANTS = [
    {
        "name": "base_strict_0.75",
        "params": {},
    },
    {
        "name": "permissive_0.75",
        "params": {"m1_timing_mode": "permissive"},
    },
    {
        "name": "relaxed_path_0.5",
        "params": {"atr_filter_threshold": 0.5},
    },
    {
        "name": "all_relaxed",
        "params": {
            "m1_timing_mode": "permissive",
            "atr_filter_threshold": 0.5,
        },
    },
    {
        "name": "strict_rr2",
        "params": {"min_rr": 2.0},
    },
]


def parse_date(value: str) -> date:
    try:
        return datetime.strptime(value, "%Y-%m-%d").date()
    except ValueError as exc:
        raise argparse.ArgumentTypeError(f"Invalid date '{value}'") from exc


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="run_gerchik_rejection_grid",
        description="Grid backtest for GerchikRejection",
    )
    p.add_argument("--symbol", required=True)
    p.add_argument("--start", required=True, type=parse_date)
    p.add_argument("--end", required=True, type=parse_date)
    p.add_argument("--allowed-energy", default="distribution,neutral,compression")
    p.add_argument("--cash", type=float, default=100_000.0)
    p.add_argument("--commission", type=float, default=0.0004)
    p.add_argument("--log-level", default="WARNING", choices=["DEBUG", "INFO", "WARNING", "ERROR"])
    return p


def _already_run(symbol, start, end, params) -> bool:
    """Check for an equivalent existing backtest (best-effort)."""
    with SessionLocal() as db:
        stmt = select(Backtest.id).where(
            Backtest.symbol == symbol,
            Backtest.strategy == "gerchik_rejection",
            Backtest.start_date == datetime.combine(start, datetime.min.time()),
            Backtest.end_date == datetime.combine(end, datetime.min.time()),
        )
        return bool(db.execute(stmt).scalars().all())


def main() -> None:
    args = build_parser().parse_args()
    logging.basicConfig(
        level=args.log_level,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        datefmt="%H:%M:%S",
    )

    allowed = [x.strip() for x in args.allowed_energy.split(",") if x.strip()]

    results = []
    for v in VARIANTS:
        name = v["name"]
        params = {"allowed_energy": allowed, **v["params"]}
        # Print directly — logger.info is hidden at WARNING level,
        # which is the default. This header is essential to read the
        # concatenated output of 5 sequential runs.
        print(f"\n{'=' * 60}")
        print(f"=== Variant: {name} ===")
        print(f"    params={v['params'] or '(defaults)'}")
        print(f"{'=' * 60}")
        logger.info("Running variant: %s (params=%s)", name, params)

        try:
            request = BacktestRequest(
                symbol=args.symbol,
                timeframe=5,
                start=args.start,
                end=args.end,
                strategy="gerchik_rejection",
                params=params,
                cash=args.cash,
                commission=args.commission,
            )
            result = run_backtest(request)
            results.append(
                {
                    "name": name,
                    "id": result.id,
                    "trades": result.trades,
                    "pnl": result.pnl,
                    "sharpe": result.sharpe,
                    "max_dd": result.max_drawdown,
                    "win_rate": result.win_rate,
                }
            )
            logger.info(
                "  OK id=%s trades=%s pnl=%.2f sharpe=%.3f",
                result.id,
                result.trades,
                result.pnl,
                result.sharpe,
            )
        except Exception as exc:
            logger.error("  FAIL %s: %s: %s", name, type(exc).__name__, exc)
            results.append({"name": name, "error": str(exc)})

    print()
    print("=" * 100)
    print(
        f"{'Variant':<24} {'id':>4} {'trades':>6} {'pnl':>10} "
        f"{'sharpe':>8} {'max_dd':>8} {'win%':>6}"
    )
    print("-" * 100)
    for r in results:
        if "error" in r:
            print(f"{r['name']:<24} FAIL: {r['error'][:60]}")
            continue
        print(
            f"{r['name']:<24} {r['id']:>4} {r['trades']:>6} "
            f"{r['pnl']:>10.2f} {r['sharpe']:>8.3f} "
            f"{r['max_dd']:>8.2f} {r['win_rate']:>6.2f}"
        )
    print("-" * 100)

    # Summary
    valid = [r for r in results if "error" not in r]
    if valid:
        print(f"\nTotal: {len(valid)}/{len(results)} succeeded")
        best = max(valid, key=lambda r: r["sharpe"])
        print(
            f"Best by sharpe: {best['name']} "
            f"(sharpe={best['sharpe']:.3f}, trades={best['trades']}, "
            f"pnl={best['pnl']:.2f})"
        )


if __name__ == "__main__":
    main()
