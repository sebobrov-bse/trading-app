"""Run SmaCrossover on real MOEX data loaded from SQLite."""

from datetime import datetime

import backtrader as bt

from app.backtest.feed import df_to_bt_feed
from app.services.candle_repository import CandleRepository
from app.strategies.sma_crossover import SmaCrossover


def main() -> None:
    """Load SBER candles, run SmaCrossover, print summary."""
    repo = CandleRepository()
    df = repo.get_dataframe(
        symbol="SBER",
        timeframe=24,
        start=datetime(2024, 1, 1),
        end=datetime(2026, 9, 28),
    )

    print(f"Bars loaded: {len(df)}")
    if df.empty:
        print("No data. Did you load SBER candles into the DB?")
        return

    print(f"Date range:  {df.index.min().date()} .. {df.index.max().date()}")

    cerebro = bt.Cerebro()
    cerebro.adddata(df_to_bt_feed(df))
    cerebro.addstrategy(SmaCrossover, fast=10, slow=30)
    cerebro.broker.setcash(100_000.0)
    cerebro.broker.setcommission(commission=0.001)
    cerebro.addsizer(bt.sizers.PercentSizer, percents=95)

    print(f"Starting Portfolio Value: {cerebro.broker.getvalue():.2f}")

    results = cerebro.run()
    strat = results[0]

    print(f"Final Portfolio Value:   {cerebro.broker.getvalue():.2f}")
    print(f"Trades in trade_log:     {len(strat.trade_log)}")

    if strat.trade_log:
        wins = sum(1 for t in strat.trade_log if t["pnl_net"] > 0)
        win_rate = wins / len(strat.trade_log) * 100
        total_pnl = sum(t["pnl_net"] for t in strat.trade_log)
        print(f"Win rate:                {win_rate:.1f}%")
        print(f"Total PnL (net):         {total_pnl:.2f}")
        print("--- First 5 trades ---")
        for t in strat.trade_log[:5]:
            print(
                f"  {t['date']}  size={t['size']:.0f}  "
                f"price={t['price']:.2f}  pnl_net={t['pnl_net']:.2f}"
            )


if __name__ == "__main__":
    main()