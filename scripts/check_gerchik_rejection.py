"""CLI: run GerchikRejection backtest and report detailed stats.

Usage:
    python -m scripts.check_gerchik_rejection \
        --symbol SBER --start 2024-06-01 --end 2024-06-30

    # With custom params:
    python -m scripts.check_gerchik_rejection --symbol SBER \
        --start 2024-06-01 --end 2024-06-30 \
        --allowed-energy distribution,neutral,compression \
        --min-rr 2.0 --timing-mode permissive
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

logger = logging.getLogger("check_rejection")


def parse_date(value: str) -> date:
    try:
        return datetime.strptime(value, "%Y-%m-%d").date()
    except ValueError as exc:
        raise argparse.ArgumentTypeError(f"Invalid date '{value}'. Expected YYYY-MM-DD.") from exc


def parse_list(value: str) -> list[str]:
    return [x.strip() for x in value.split(",") if x.strip()]


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="check_gerchik_rejection",
        description="Run GerchikRejection backtest and print detailed stats",
    )
    p.add_argument("--symbol", required=True)
    p.add_argument("--start", required=True, type=parse_date)
    p.add_argument("--end", required=True, type=parse_date)
    p.add_argument(
        "--allowed-energy",
        default="distribution,neutral,compression",
        type=parse_list,
    )
    p.add_argument("--cash", type=float, default=100_000.0)
    p.add_argument("--commission", type=float, default=0.0004)
    p.add_argument(
        "--log-level",
        default="WARNING",
        choices=["DEBUG", "INFO", "WARNING", "ERROR"],
    )
    return p


def _report_backtest(bt_id: int) -> None:
    """Print backtest details and trade meta distribution from DB."""
    with SessionLocal() as db:
        bt = db.get(Backtest, bt_id)
        if bt is None:
            print(f"Backtest id={bt_id} not found")
            return

        print(f"\n=== Backtest id={bt.id} ({bt.strategy} {bt.symbol}) ===")
        print(f"period: {bt.start_date.date()} .. {bt.end_date.date()}")
        print(f"bars={bt.bars}  trades={bt.trades_count}")
        print(f"pnl={float(bt.pnl):.2f}  pnl_pct={float(bt.pnl_percent):.2f}%")
        print(
            f"sharpe={float(bt.sharpe):.3f}  sortino={float(bt.sortino):.3f}  "
            f"calmar={float(bt.calmar):.3f}"
        )
        print(f"max_dd={float(bt.max_drawdown):.2f}%  win_rate={float(bt.win_rate):.2f}%")
        print(f"profit_factor={float(bt.profit_factor):.3f}")
        print(f"final_value={float(bt.final_value):.2f}")

        # Trade meta distribution
        stmt = select(BacktestTrade).where(BacktestTrade.backtest_id == bt.id)
        trades = db.execute(stmt).scalars().all()

        if not trades:
            print("\nNo closed trades.")
            return

        print(f"\nClosed trades: {len(trades)}")
        for i, t in enumerate(trades[:20]):
            print(
                f"  [{i}] entry={t.entry_time} exit={t.exit_time} "
                f"pnl={float(t.pnl):.2f} pnl_net={float(t.pnl_net):.2f} "
                f"pattern={t.pattern!r} score={t.level_score} "
                f"energy={t.energy!r} path={float(t.path_ratio) if t.path_ratio else None}"
            )
        if len(trades) > 20:
            print(f"  ... and {len(trades) - 20} more")

        # Sanity: realized pnl from trades vs. reported pnl (final - start)
        realized = sum(float(t.pnl_net) for t in trades)
        reported = float(bt.pnl)
        unrealized = reported - realized
        print(f"\nPnL breakdown:")
        print(f"  realized (closed trades): {realized:+.2f}")
        print(f"  reported (bt.pnl):        {reported:+.2f}")
        print(f"  unrealized:               {unrealized:+.2f}")
        if abs(unrealized) > max(abs(realized) * 0.5, 100):
            print(f"  ⚠  WARNING: unrealized != 0 — position open at end?")
            print(f"     (this is a bug: intraday_only should close all)")

        # Distribution by energy
        by_energy: dict[str, list[float]] = {}

        # Distribution by energy
        by_energy: dict[str, list[float]] = {}
        by_score: dict[int, list[float]] = {}
        for t in trades:
            e = t.energy or "None"
            by_energy.setdefault(e, []).append(float(t.pnl_net))
            s = t.level_score if t.level_score is not None else -1
            by_score.setdefault(s, []).append(float(t.pnl_net))

        print("\nPnL by energy:")
        for e, pnls in sorted(by_energy.items()):
            wins = sum(1 for p in pnls if p > 0)
            print(
                f"  {e:16} count={len(pnls):2}  "
                f"win={wins}/{len(pnls)}  sum={sum(pnls):.2f}  "
                f"avg={sum(pnls) / len(pnls):.2f}"
            )

        print("\nPnL by level_score:")
        for s, pnls in sorted(by_score.items()):
            wins = sum(1 for p in pnls if p > 0)
            label = f"{s}" if s >= 0 else "None"
            print(
                f"  score={label:4} count={len(pnls):2}  "
                f"win={wins}/{len(pnls)}  sum={sum(pnls):.2f}  "
                f"avg={sum(pnls) / len(pnls):.2f}"
            )


def main() -> None:
    args = build_parser().parse_args()
    logging.basicConfig(
        level=args.log_level,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        datefmt="%H:%M:%S",
    )

    if args.start > args.end:
        raise SystemExit("--start must be <= --end")

    request = BacktestRequest(
        symbol=args.symbol,
        timeframe=5,  # semantic: primary is M1, resampled to M5
        start=args.start,
        end=args.end,
        strategy="gerchik_rejection",
        params={
            "allowed_energy": args.allowed_energy,
        },
        cash=args.cash,
        commission=args.commission,
    )

    print(f"Running GerchikRejection: {args.symbol} {args.start}..{args.end}")
    print(f"  allowed_energy={args.allowed_energy}")
    result = run_backtest(request)
    print(f"\nNew backtest id={result.id}")

    if result.id is not None:
        _report_backtest(result.id)


if __name__ == "__main__":
    main()
