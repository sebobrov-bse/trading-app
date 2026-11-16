"""Grid backtest for GerchikBreakout across config variants.

Usage:
    python -m scripts.run_gerchik_breakout_grid \
        --symbol SBER --start 2024-06-01 --end 2024-12-30
"""

import argparse
import logging
from datetime import date, datetime

from app.schemas.backtest import BacktestRequest
from app.services.backtest_service import run_backtest

logger = logging.getLogger("breakout_grid")


VARIANTS = [
    {"name": "base", "params": {}},
    {"name": "longer_wait", "params": {"breakout_max_wait_bars": 24}},
    {"name": "relaxed_path", "params": {"atr_filter_threshold": 0.5}},
    {"name": "wider_cancel", "params": {"breakout_cancel_distance": 3.0}},
    {"name": "wider_stop", "params": {"stop_loss_pct": 0.003}},
    {
        "name": "combo",
        "params": {
            "breakout_max_wait_bars": 24,
            "breakout_cancel_distance": 3.0,
            "stop_loss_pct": 0.003,
            "atr_filter_threshold": 0.5,
        },
    },
]


def parse_date(value: str) -> date:
    try:
        return datetime.strptime(value, "%Y-%m-%d").date()
    except ValueError as exc:
        raise argparse.ArgumentTypeError(f"Invalid date '{value}'") from exc


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="run_gerchik_breakout_grid",
        description="Grid backtest for GerchikBreakout",
    )
    p.add_argument("--symbol", required=True)
    p.add_argument("--start", required=True, type=parse_date)
    p.add_argument("--end", required=True, type=parse_date)
    p.add_argument("--allowed-energy", default="accumulation,compression")
    p.add_argument("--cash", type=float, default=100_000.0)
    p.add_argument("--commission", type=float, default=0.0004)
    p.add_argument("--log-level", default="WARNING", choices=["DEBUG", "INFO", "WARNING", "ERROR"])
    return p


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
        print(f"\n{'=' * 60}")
        print(f"=== Variant: {name} ===")
        print(f"    params={v['params'] or '(defaults)'}")
        print(f"{'=' * 60}")

        try:
            request = BacktestRequest(
                symbol=args.symbol,
                timeframe=5,
                start=args.start,
                end=args.end,
                strategy="gerchik_breakout",
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
                "OK id=%s trades=%s pnl=%.2f sharpe=%.3f",
                result.id,
                result.trades,
                result.pnl,
                result.sharpe,
            )
        except Exception as exc:
            logger.error("FAIL %s: %s: %s", name, type(exc).__name__, exc)
            results.append({"name": name, "error": str(exc)})

    print()
    print("=" * 100)
    print(
        f"{'Variant':<16} {'id':>4} {'trades':>6} {'pnl':>10} "
        f"{'sharpe':>8} {'max_dd':>8} {'win%':>6}"
    )
    print("-" * 100)
    for r in results:
        if "error" in r:
            print(f"{r['name']:<16} FAIL: {r['error'][:60]}")
            continue
        print(
            f"{r['name']:<16} {r['id']:>4} {r['trades']:>6} "
            f"{r['pnl']:>10.2f} {r['sharpe']:>8.3f} "
            f"{r['max_dd']:>8.2f} {r['win_rate']:>6.2f}"
        )
    print("-" * 100)

    valid = [r for r in results if "error" not in r]
    if valid:
        print(f"\nTotal: {len(valid)}/{len(results)} succeeded")
        best = max(valid, key=lambda r: r["pnl"])
        print(f"Best by pnl: {best['name']} (trades={best['trades']}, pnl={best['pnl']:.2f})")
        most = max(valid, key=lambda r: r["trades"])
        print(f"Most trades: {most['name']} ({most['trades']} trades)")


if __name__ == "__main__":
    main()
