"""Test SmaCrossover on synthetic random-walk data."""

import backtrader as bt
import numpy as np
import pandas as pd

from app.strategies.sma_crossover import SmaCrossover


def make_synthetic_df(n: int = 500, seed: int = 42) -> pd.DataFrame:
    """Generate a random walk with a slight upward drift."""
    rng = np.random.default_rng(seed)

    returns = rng.normal(loc=0.0005, scale=0.01, size=n)
    close = 100.0 * np.exp(np.cumsum(returns))

    noise = rng.normal(loc=0.0, scale=0.002, size=n)
    open_ = close * (1 + noise)
    high = np.maximum(open_, close) * (1 + np.abs(noise))
    low = np.minimum(open_, close) * (1 - np.abs(noise))
    volume = rng.integers(1000, 10_000, size=n)

    dates = pd.date_range("2024-01-01", periods=n, freq="B")
    return pd.DataFrame(
        {
            "open": open_,
            "high": high,
            "low": low,
            "close": close,
            "volume": volume,
        },
        index=dates,
    )


def main() -> None:
    """Run the backtest and print summary."""
    df = make_synthetic_df(n=500)

    cerebro = bt.Cerebro()
    cerebro.adddata(bt.feeds.PandasData(dataname=df))
    cerebro.addstrategy(SmaCrossover, fast=10, slow=30)
    cerebro.broker.setcash(100_000.0)
    cerebro.broker.setcommission(commission=0.001)
    cerebro.addsizer(bt.sizers.PercentSizer, percents=95)

    print(f"Bars: {len(df)}")
    print(f"Starting Portfolio Value: {cerebro.broker.getvalue():.2f}")

    results = cerebro.run()
    strat = results[0]

    print(f"Final Portfolio Value:   {cerebro.broker.getvalue():.2f}")
    print(f"Trades in trade_log:     {len(strat.trade_log)}")

    if strat.trade_log:
        wins = sum(1 for t in strat.trade_log if t["pnl_net"] > 0)
        win_rate = wins / len(strat.trade_log) * 100
        print(f"Win rate:                {win_rate:.1f}%")
        print("--- First 5 trades ---")
        for t in strat.trade_log[:5]:
            print(
                f"  {t['date']}  size={t['size']:.0f}  "
                f"price={t['price']:.2f}  pnl_net={t['pnl_net']:.2f}"
            )


if __name__ == "__main__":
    main()