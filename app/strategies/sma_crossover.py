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
        # BaseStrategy._on_bar_start() already handles:
        # - bars_in_market counter
        # - risk.on_new_bar()
        # - _update_dynamic_levels() (breakeven, trailing)
        super().next()

        if self.order:
            return

        if not self.position:
            if self.crossover > 0:
                self.safe_buy(direction="long")
        else:
            if self.crossover < 0:
                self.safe_close()
