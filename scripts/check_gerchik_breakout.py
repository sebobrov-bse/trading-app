"""CLI: run GerchikBreakout and compare with GerchikRejection on same data.

Usage:
    python -m scripts.check_gerchik_breakout \
        --symbol SBER --start 2024-06-01 --end 2024-12-30
"""

import argparse
import logging
from datetime import date, datetime

from sqlalchemy import select

from app.db.session import SessionLocal
from app.models.backtest import Backtest
from app.models.backtest_trade import BacktestTrade
from app.schemas.backtest import BacktestRequest
from app.services.backtest_service import run_backtest

logger = logging.getLogger("check_breakout")


def parse_date(value: str) -> date:
    try:
        return datetime.strptime(value, "%Y-%m-%d").date()
    except ValueError as exc:
        raise argparse.ArgumentTypeError(f"Invalid date '{value}'") from exc


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="check_gerchik_breakout",
        description="Run GerchikBreakout and compare with GerchikRejection",
    )
    p.add_argument("--symbol", required=True)
    p.add_argument("--start", required=True, type=parse_date)
    p.add_argument("--end", required=True, type=parse_date)
    p.add_argument("--cash", type=float, default=100_000.0)
    p.add_argument("--commission", type=float, default=0.0004)
    p.add_argument(
        "--log-level",
        default="WARNING",
        choices=["DEBUG", "INFO", "WARNING", "ERROR"],
    )
    return p


def _run_variant(
    name: str,
    symbol: str,
    start: date,
    end: date,
    strategy: str,
    allowed_energy: list[str],
    cash: float,
    commission: float,
) -> dict | None:
    """Run one backtest, return summary dict (or None on fail)."""
    print(f"\n=== {name} ({strategy}) ===")
    request = BacktestRequest(
        symbol=symbol,
        timeframe=5,
        start=start,
        end=end,
        strategy=strategy,
        params={"allowed_energy": allowed_energy},
        cash=cash,
        commission=commission,
    )
    try:
        result = run_backtest(request)
    except Exception as exc:
        print(f"  FAIL: {type(exc).__name__}: {exc}")
        return None

    print(
        f"  id={result.id}  trades={result.trades}  "
        f"pnl={result.pnl:.2f}  sharpe={result.sharpe:.3f}"
    )

    if result.id is None:
        return None

    # Realized pnl (sum of closed trades).
    with SessionLocal() as db:
        bt = db.get(Backtest, result.id)
        stmt = select(BacktestTrade).where(BacktestTrade.backtest_id == result.id)
        trades = db.execute(stmt).scalars().all()
        realized = sum(float(t.pnl_net) for t in trades)
        unrealized = float(bt.pnl) - realized if bt else 0.0

        print(f"  realized (closed) = {realized:+.2f}")
        print(f"  unrealized        = {unrealized:+.2f}")

        if trades:
            wins = sum(1 for t in trades if float(t.pnl_net) > 0)
            print(
                f"  closed trades = {len(trades)}, wins = {wins}, "
                f"win_rate = {100 * wins / len(trades):.1f}%"
            )
            print(f"  patterns: ", end="")
            from collections import Counter

            patterns = Counter(t.pattern or "None" for t in trades)
            print(dict(patterns))

        return {
            "name": name,
            "id": result.id,
            "trades": result.trades,
            "pnl": result.pnl,
            "realized": realized,
            "unrealized": unrealized,
            "sharpe": result.sharpe,
            "max_dd": result.max_drawdown,
            "win_rate": result.win_rate,
        }


def main() -> None:
    args = build_parser().parse_args()
    logging.basicConfig(
        level=args.log_level,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        datefmt="%H:%M:%S",
    )

    if args.start > args.end:
        raise SystemExit("--start must be <= --end")

    # Rejection (S.2b) — for comparison.
    rejection = _run_variant(
        "Rejection",
        args.symbol,
        args.start,
        args.end,
        "gerchik_rejection",
        ["distribution", "neutral", "compression"],
        args.cash,
        args.commission,
    )

    # Breakout (S.2c).
    breakout = _run_variant(
        "Breakout",
        args.symbol,
        args.start,
        args.end,
        "gerchik_breakout",
        ["accumulation", "compression"],
        args.cash,
        args.commission,
    )

    # Comparison table.
    print("\n" + "=" * 100)
    print(
        f"{'Strategy':<12} {'trades':>6} {'pnl':>10} {'realized':>10} "
        f"{'unreal':>10} {'sharpe':>8} {'max_dd':>8} {'win%':>6}"
    )
    print("-" * 100)
    for r in (rejection, breakout):
        if r is None:
            print(f"{'FAIL':<12}")
            continue
        print(
            f"{r['name']:<12} {r['trades']:>6} {r['pnl']:>10.2f} "
            f"{r['realized']:>10.2f} {r['unrealized']:>10.2f} "
            f"{r['sharpe']:>8.3f} {r['max_dd']:>8.2f} {r['win_rate']:>6.2f}"
        )
    print("=" * 100)

    # Verdict.
    if rejection and breakout:
        r_tr = rejection["trades"]
        b_tr = breakout["trades"]
        r_pnl = rejection["realized"]
        b_pnl = breakout["realized"]
        print(f"\nVerdict:")
        print(
            f"  trades:    rejection={r_tr}  breakout={b_tr}  "
            f"→ {'breakout' if b_tr > r_tr else 'rejection'} more active"
        )
        print(
            f"  realized:  rejection={r_pnl:+.2f}  breakout={b_pnl:+.2f}  "
            f"→ {'rejection' if r_pnl > b_pnl else 'breakout'} more profitable"
        )


if __name__ == "__main__":
    main()
