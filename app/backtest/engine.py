"""Backtest engine: run a strategy on a DataFrame and collect metrics."""

from dataclasses import dataclass

import backtrader as bt
import pandas as pd

from app.strategies.sma_crossover import SmaCrossover


@dataclass
class BacktestResult:
    """Metrics returned by a backtest run."""

    start_value: float
    final_value: float
    total_return_pct: float
    max_drawdown_pct: float
    sharpe_ratio: float | None
    total_trades: int
    won_trades: int
    lost_trades: int
    win_rate_pct: float | None


def run_backtest(
    df: pd.DataFrame,
    cash: float = 100_000.0,
    commission: float = 0.001,
    fast: int = 10,
    slow: int = 30,
) -> BacktestResult:
    """Run SmaCrossover on the given DataFrame. Returns a BacktestResult."""
    if df.empty:
        raise ValueError("Empty DataFrame — no data to backtest.")

    cerebro = bt.Cerebro()
    cerebro.adddata(bt.feeds.PandasData(dataname=df))
    cerebro.addstrategy(SmaCrossover, fast=fast, slow=slow)
    cerebro.broker.setcash(cash)
    cerebro.broker.setcommission(commission=commission)

    cerebro.addanalyzer(bt.analyzers.DrawDown, _name="dd")
    cerebro.addanalyzer(bt.analyzers.SharpeRatio, _name="sharpe", riskfreerate=0.0)
    cerebro.addanalyzer(bt.analyzers.TradeAnalyzer, _name="trades")

    start_value = cerebro.broker.getvalue()
    results = cerebro.run()
    final_value = cerebro.broker.getvalue()

    strat = results[0]
    dd = strat.analyzers.dd.get_analysis()
    sharpe = strat.analyzers.sharpe.get_analysis()
    trades = strat.analyzers.trades.get_analysis()

    total = trades.get("total", {}).get("closed", 0)
    won = trades.get("won", {}).get("total", 0)
    lost = trades.get("lost", {}).get("total", 0)
    win_rate = (won / total * 100) if total else None

    return BacktestResult(
        start_value=start_value,
        final_value=final_value,
        total_return_pct=(final_value - start_value) / start_value * 100,
        max_drawdown_pct=dd.get("max", {}).get("drawdown", 0.0),
        sharpe_ratio=sharpe.get("sharperatio"),
        total_trades=total,
        won_trades=won,
        lost_trades=lost,
        win_rate_pct=win_rate,
    )