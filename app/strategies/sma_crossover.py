"""SMA crossover strategy: buy on fast-over-slow, close on reverse."""

import backtrader as bt

from app.strategies.base import BaseStrategy


class SmaCrossover(BaseStrategy):
    """Classic SMA crossover.

    BUY when fast SMA crosses above slow SMA.
    SELL (close) when fast SMA crosses below slow SMA.
    """

    params = (
        ("fast", 10),
        ("slow", 30),
    )

    def __init__(self) -> None:
        super().__init__()
        self.fast_sma = bt.indicators.SMA(self.data.close, period=self.p.fast)
        self.slow_sma = bt.indicators.SMA(self.data.close, period=self.p.slow)
        # crossover > 0: fast crossed above slow (BUY signal)
        # crossover < 0: fast crossed below slow (SELL signal)
        self.crossover = bt.indicators.CrossOver(self.fast_sma, self.slow_sma)

    def next(self) -> None:
        """Called by the engine on each bar."""
        if self.position:
            self.bars_in_market += 1

        if self.order:
            return  # order in flight, wait

        if not self.position:
            if self.crossover > 0:
                self.order = self.buy()
        else:
            if self.crossover < 0:
                self.order = self.close()
