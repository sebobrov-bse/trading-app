"""Compare SmaCrossover with and without risk management.

Runs the same strategy on the same data twice:
- run A: use_risk_management=False (old behaviour)
- run B: use_risk_management=True  (default RiskConfig)

Prints metrics side by side.
"""

from datetime import date

import backtrader as bt

from app.backtest.feed import df_to_bt_feed
from app.risk.config import RiskConfig
from app.services.candle_repository import CandleRepository
from app.strategies.sma_crossover import SmaCrossover


def run_one(
    df,
    risk_config: RiskConfig,
    label: str,
) -> dict:
    """Run a single backtest and return a metrics dict."""
    cerebro = bt.Cerebro(runonce=False)
    cerebro.adddata(df_to_bt_feed(df))
    cerebro.addstrategy(
        SmaCrossover,
        fast=10,
        slow=30,
        risk_config=risk_config,
    )
    cerebro.broker.setcash(100_000.0)
    cerebro.broker.setcommission(commission=0.001)
    cerebro.addsizer(bt.sizers.PercentSizer, percents=95)

    cerebro.addanalyzer(bt.analyzers.TradeAnalyzer, _name="trades")
    cerebro.addanalyzer(bt.analyzers.DrawDown, _name="dd")

    print(f"\n=== {label} ===")
    print(f"Starting Portfolio Value: {cerebro.broker.getvalue():.2f}")

    results = cerebro.run()
    strat = results[0]
    final_value = cerebro.broker.getvalue()

    ta = strat.analyzers.trades.get_analysis()
    dd = strat.analyzers.dd.get_analysis()

    total = int(ta.get("total", {}).get("closed", 0) or 0)
    won = int(ta.get("won", {}).get("total", 0) or 0)
    lost = int(ta.get("lost", {}).get("total", 0) or 0)
    win_rate = (won / total) if total else 0.0
    max_dd = float(dd.get("max", {}).get("drawdown", 0.0) or 0.0)

    stats = {
        "label": label,
        "final_value": final_value,
        "pnl": final_value - 100_000.0,
        "pnl_pct": (final_value - 100_000.0) / 100_000.0 * 100.0,
        "trades": total,
        "won": won,
        "lost": lost,
        "win_rate": win_rate,
        "max_dd": max_dd,
    }

    # Risk-specific stats.
    if strat.risk is not None:
        rs = strat.risk.get_stats()
        stats.update(
            {
                "stops_hit": rs.get("stops_hit", 0),
                "take_profits_hit": rs.get("take_profits_hit", 0),
                "skipped_by_atr": rs.get("skipped_by_atr", 0),
                "skipped_by_size_zero": rs.get("skipped_by_size_zero", 0),
                "max_consecutive_losses": rs.get("max_consecutive_losses", 0),
                "avg_risk_per_trade": rs.get("avg_risk_per_trade", 0.0),
            }
        )
    else:
        stats.update(
            {
                "stops_hit": 0,
                "take_profits_hit": 0,
                "skipped_by_atr": 0,
                "skipped_by_size_zero": 0,
                "max_consecutive_losses": 0,
                "avg_risk_per_trade": 0.0,
            }
        )

    print(f"Final Portfolio Value:   {final_value:.2f}")
    print(f"PnL:                     {stats['pnl']:.2f} ({stats['pnl_pct']:.2f}%)")
    print(f"Trades:                  {total} (won {won}, lost {lost})")
    print(f"Win Rate:                {win_rate * 100:.1f}%")
    print(f"Max Drawdown:            {max_dd:.2f}%")
    print(f"Stops hit:               {stats['stops_hit']}")
    print(f"Take-profits hit:        {stats['take_profits_hit']}")
    print(f"Skipped by ATR:          {stats['skipped_by_atr']}")
    print(f"Skipped (size=0):        {stats['skipped_by_size_zero']}")
    print(f"Max consecutive losses:  {stats['max_consecutive_losses']}")
    print(f"Avg risk per trade:      {stats['avg_risk_per_trade']:.3f}%")

    return stats


def main() -> None:
    # Load SBER daily candles.
    repo = CandleRepository()
    df = repo.get_dataframe(
        symbol="SBER",
        timeframe=24,
        start=date(2024, 1, 1),
        end=date(2026, 9, 28),
    )

    if df.empty:
        print("No data. Load SBER candles first.")
        return

    print(f"Loaded {len(df)} candles for SBER.")

    # Run without risk management.
    cfg_off = RiskConfig(use_risk_management=False)
    stats_off = run_one(df, cfg_off, "WITHOUT risk management")

    # Run with default risk management.
    cfg_on = RiskConfig(use_risk_management=True)
    stats_on = run_one(df, cfg_on, "WITH risk management")

    # Summary table.
    print("\n" + "=" * 60)
    print(f"{'Metric':<26} {'OFF':>15} {'ON':>15}")
    print("-" * 60)

    rows = [
        ("Final value", "final_value", "{:.0f}"),
        ("PnL", "pnl", "{:+.0f}"),
        ("PnL %", "pnl_pct", "{:+.2f}"),
        ("Trades", "trades", "{:d}"),
        ("Win rate %", "win_rate", "{:.1f}"),
        ("Max drawdown %", "max_dd", "{:.2f}"),
        ("Stops hit", "stops_hit", "{:d}"),
        ("Take-profits hit", "take_profits_hit", "{:d}"),
        ("Skipped by ATR", "skipped_by_atr", "{:d}"),
        ("Skipped (size=0)", "skipped_by_size_zero", "{:d}"),
        ("Max consec. losses", "max_consecutive_losses", "{:d}"),
        ("Avg risk / trade %", "avg_risk_per_trade", "{:.3f}"),
    ]

    for label, key, fmt in rows:
        off_val = stats_off[key]
        on_val = stats_on[key]
        if key == "win_rate":
            off_val *= 100
            on_val *= 100
        print(f"{label:<26} {fmt.format(off_val):>15} {fmt.format(on_val):>15}")


if __name__ == "__main__":
    main()
