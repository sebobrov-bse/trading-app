"""Minimal Backtrader 'Hello World' backtest on synthetic data."""

import backtrader as bt
import pandas as pd


class SimpleStrategy(bt.Strategy):
    """Buy on every bar, sell on the next one."""

    def next(self):
        if not self.position:
            self.buy()
        else:
            self.sell()


def make_synthetic_df(n: int = 10) -> pd.DataFrame:
    """Build a small DataFrame with OHLCV data and a datetime index."""
    dates = pd.date_range("2024-01-01", periods=n, freq="D")
    return pd.DataFrame(
        {
            "open": [100.0 + i for i in range(n)],
            "high": [105.0 + i for i in range(n)],
            "low": [95.0 + i for i in range(n)],
            "close": [102.0 + i for i in range(n)],
            "volume": [1000 + i for i in range(n)],
        },
        index=dates,
    )


def main() -> None:
    """Set up and run the backtest."""
    df = make_synthetic_df(10)

    cerebro = bt.Cerebro()
    cerebro.adddata(bt.feeds.PandasData(dataname=df))
    cerebro.addstrategy(SimpleStrategy)
    cerebro.broker.setcash(10000.0)
    cerebro.broker.setcommission(commission=0.001)

    cerebro.addanalyzer(bt.analyzers.TradeAnalyzer, _name="trades")

    print("Starting Portfolio Value: %.2f" % cerebro.broker.getvalue())
    results = cerebro.run()
    print("Final Portfolio Value: %.2f" % cerebro.broker.getvalue())

    strat = results[0]
    trade_info = strat.analyzers.trades.get_analysis()
    total = trade_info.get("total", {}).get("closed", 0)
    print(f"Closed trades: {total}")


if __name__ == "__main__":
    main()