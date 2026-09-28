"""Backtest service: load data, run a strategy, return metrics."""

import logging
from typing import Any

import backtrader as bt

from app.backtest.feed import df_to_bt_feed
from app.schemas.backtest import BacktestRequest, BacktestResult
from app.services.candle_repository import CandleRepository
from app.strategies.sma_crossover import SmaCrossover

logger = logging.getLogger(__name__)

# Strategy registry: add new strategies here, endpoint stays unchanged.
STRATEGY_REGISTRY: dict[str, type[bt.Strategy]] = {
    "sma_crossover": SmaCrossover,
}


def _validate_params(strategy_name: str, params: dict[str, Any]) -> dict[str, Any]:
    """Validate and normalize strategy params.

    Raises ValueError with a clear message on bad input.
    """
    if strategy_name == "sma_crossover":
        try:
            fast = int(params.get("fast", 10))
            slow = int(params.get("slow", 30))
        except (TypeError, ValueError) as exc:
            raise ValueError("fast and slow must be integers") from exc

        if fast < 2 or slow < 3:
            raise ValueError("fast must be >= 2, slow must be >= 3")
        if fast >= slow:
            raise ValueError("fast must be less than slow")
        return {"fast": fast, "slow": slow}

    # Unknown strategies get their params passed through.
    return dict(params)


def run_backtest(request: BacktestRequest) -> BacktestResult:
    """Load candles, run the strategy, return metrics.

    Synchronous — call via run_in_threadpool from the async endpoint,
    because Backtrader is CPU-bound and blocks the event loop.
    """
    if request.strategy not in STRATEGY_REGISTRY:
        raise ValueError(f"Unknown strategy: {request.strategy}")

    params = _validate_params(request.strategy, request.params)

    repo = CandleRepository()
    df = repo.get_dataframe(
        symbol=request.symbol,
        timeframe=request.timeframe,
        start=request.start,
        end=request.end,
    )

    if df.empty:
        # Empty result is valid — client sees bars: 0.
        return BacktestResult(
            symbol=request.symbol,
            timeframe=request.timeframe,
            start=request.start,
            end=request.end,
            strategy=request.strategy,
            params=params,
            bars=0,
            trades=0,
            final_value=request.cash,
            pnl=0.0,
            pnl_percent=0.0,
            win_rate=0.0,
            max_drawdown=0.0,
        )

    cerebro = bt.Cerebro()
    cerebro.adddata(df_to_bt_feed(df))
    cerebro.addstrategy(STRATEGY_REGISTRY[request.strategy], **params)
    cerebro.broker.setcash(request.cash)
    cerebro.broker.setcommission(commission=request.commission)
    cerebro.addsizer(bt.sizers.PercentSizer, percents=95)

    cerebro.addanalyzer(bt.analyzers.TradeAnalyzer, _name="trades")
    cerebro.addanalyzer(bt.analyzers.DrawDown, _name="dd")

    start_value = cerebro.broker.getvalue()
    results = cerebro.run()
    final_value = cerebro.broker.getvalue()

    strat = results[0]
    ta = strat.analyzers.trades.get_analysis()
    dd = strat.analyzers.dd.get_analysis()

    total = ta.get("total", {}).get("closed", 0)
    won = ta.get("won", {}).get("total", 0)
    win_rate = (won / total) if total else 0.0

    return BacktestResult(
        symbol=request.symbol,
        timeframe=request.timeframe,
        start=request.start,
        end=request.end,
        strategy=request.strategy,
        params=params,
        bars=len(df),
        trades=total,
        final_value=final_value,
        pnl=final_value - start_value,
        pnl_percent=(final_value - start_value) / start_value * 100,
        win_rate=win_rate,
        max_drawdown=dd.get("max", {}).get("drawdown", 0.0),
    )