"""CLI: compare 3 Gerchik patterns on same data."""
import argparse
from datetime import datetime

from app.schemas.backtest import BacktestRequest
from app.services.backtest_service import run_backtest


def parse_date(v):
    return datetime.strptime(v, "%Y-%m-%d").date()


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--symbol", required=True)
    p.add_argument("--start", required=True, type=parse_date)
    p.add_argument("--end", required=True, type=parse_date)
    args = p.parse_args()

    variants = [
        ("Rejection", "gerchik_rejection",
         ["distribution", "neutral", "compression"]),
        ("Breakout", "gerchik_breakout",
         ["accumulation", "compression"]),
        ("FalseBreakout", "gerchik_false_breakout",
         ["distribution", "accumulation", "compression"]),
    ]

    print(f"\n{'Strategy':<16} {'id':>4} {'trades':>6} {'pnl':>10} {'sharpe':>8}")
    print("-" * 60)

    for name, strat, energy in variants:
        req = BacktestRequest(
            symbol=args.symbol,
            timeframe=5,
            start=args.start,
            end=args.end,
            strategy=strat,
            params={"allowed_energy": energy},
            cash=100000.0,
            commission=0.0004,
        )
        try:
            r = run_backtest(req)
            print(f"{name:<16} {r.id or 0:>4} {r.trades:>6} "
                  f"{r.pnl:>10.2f} {r.sharpe:>8.3f}")
        except Exception as e:
            print(f"{name:<16} FAIL: {e}")


if __name__ == "__main__":
    main()