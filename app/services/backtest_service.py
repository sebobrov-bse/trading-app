"""Backtest service: load data, run a strategy, return metrics."""

import logging
import math
from datetime import date
from typing import Any

import backtrader as bt
import numpy as np

from app.backtest.feed import df_to_bt_feed
from app.schemas.backtest import (
    BacktestRequest,
    BacktestResult,
    EquityPoint,
    TradeInfo,
)
from app.services.candle_repository import CandleRepository
from app.strategies.sma_crossover import SmaCrossover

logger = logging.getLogger(__name__)

STRATEGY_REGISTRY: dict[str, type[bt.Strategy]] = {
    "sma_crossover": SmaCrossover,
}

TRADING_DAYS_PER_YEAR = 252


def _validate_params(strategy_name: str, params: dict[str, Any]) -> dict[str, Any]:
    """Validate and normalize strategy params."""
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

    return dict(params)


def _safe_float(x: Any, default: float = 0.0) -> float:
    """Return a float, replacing nan/inf/None with default."""
    try:
        v = float(x)
    except (TypeError, ValueError):
        return default
    if math.isnan(v) or math.isinf(v):
        return default
    return v


def _empty_result(request: BacktestRequest, params: dict) -> BacktestResult:
    """Build a zero-filled result for an empty data range."""
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
        cagr=0.0,
        max_drawdown=0.0,
        sharpe=0.0,
        sortino=0.0,
        calmar=0.0,
        win_rate=0.0,
        profit_factor=0.0,
        avg_win=0.0,
        avg_loss=0.0,
        exposure=0.0,
        equity_curve=[],
        trades_list=[],
    )


def _compute_sortino(returns: list[float]) -> float:
    """Annualized Sortino ratio from per-bar returns.

    Sortino uses only negative returns for the denominator.
    """
    if not returns:
        return 0.0
    arr = np.asarray(returns, dtype=float)
    arr = arr[~np.isnan(arr)]
    if arr.size < 2:
        return 0.0

    mean_ret = float(np.mean(arr))
    downside = arr[arr < 0]
    if downside.size == 0:
        return 0.0
    downside_std = float(np.std(downside))
    if downside_std == 0:
        return 0.0

    return mean_ret / downside_std * math.sqrt(TRADING_DAYS_PER_YEAR)


def _compute_cagr(initial: float, final: float, start: date, end: date) -> float:
    """Compound annual growth rate."""
    if initial <= 0 or final <= 0:
        return 0.0
    days = (end - start).days
    if days <= 0:
        return 0.0
    years = days / 365.25
    if years <= 0:
        return 0.0
    return (final / initial) ** (1.0 / years) - 1.0


def run_backtest(request: BacktestRequest) -> BacktestResult:
    """Load candles, run the strategy, return extended metrics."""
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
        return _empty_result(request, params)

    cerebro = bt.Cerebro(runonce=False)
    cerebro.adddata(df_to_bt_feed(df))
    cerebro.addstrategy(STRATEGY_REGISTRY[request.strategy], **params)
    cerebro.broker.setcash(request.cash)
    cerebro.broker.setcommission(commission=request.commission)
    cerebro.addsizer(bt.sizers.PercentSizer, percents=95)

    # Track portfolio value on every bar for the equity curve.
    cerebro.addobserver(bt.observers.Value)

    cerebro.addanalyzer(bt.analyzers.TradeAnalyzer, _name="trades")
    cerebro.addanalyzer(bt.analyzers.DrawDown, _name="dd")
    cerebro.addanalyzer(
        bt.analyzers.TimeReturn,
        _name="returns",
        timeframe=bt.TimeFrame.Days,
    )
    cerebro.addanalyzer(
        bt.analyzers.SharpeRatio,
        _name="sharpe",
        timeframe=bt.TimeFrame.Days,
        riskfreerate=0.0,
        annualize=True,
        factor=TRADING_DAYS_PER_YEAR,
    )

    start_value = cerebro.broker.getvalue()
    results = cerebro.run()
    final_value = cerebro.broker.getvalue()

    strat = results[0]
    ta = strat.analyzers.trades.get_analysis()
    dd = strat.analyzers.dd.get_analysis()
    returns_an = strat.analyzers.returns.get_analysis()
    sharpe_an = strat.analyzers.sharpe.get_analysis()

    total = int(ta.get("total", {}).get("closed", 0) or 0)
    won = int(ta.get("won", {}).get("total", 0) or 0)
    lost = int(ta.get("lost", {}).get("total", 0) or 0)

    won_pnl_total = _safe_float(ta.get("won", {}).get("pnl", {}).get("total", 0.0))
    lost_pnl_total = _safe_float(ta.get("lost", {}).get("pnl", {}).get("total", 0.0))
    avg_win = _safe_float(ta.get("won", {}).get("pnl", {}).get("average", 0.0))
    avg_loss = _safe_float(ta.get("lost", {}).get("pnl", {}).get("average", 0.0))

    gross_loss = abs(lost_pnl_total)
    profit_factor = (won_pnl_total / gross_loss) if gross_loss > 0 else 0.0

    win_rate = (won / total) if total else 0.0

    max_dd = _safe_float(dd.get("max", {}).get("drawdown", 0.0))
    sharpe = _safe_float(sharpe_an.get("sharperatio"))

    # Per-bar returns for Sortino.
    returns_list = [float(v) for v in returns_an.values()]
    sortino = _compute_sortino(returns_list)

    cagr = _compute_cagr(start_value, final_value, request.start, request.end)
    calmar = (cagr / (max_dd / 100.0)) if max_dd > 0 else 0.0

    exposure = strat.bars_in_market / len(strat) if len(strat) > 0 else 0.0

    # Equity curve: one value per bar, plus timestamps.
    values_arr = list(strat.observers.value.lines.value.array)
    dts_arr = list(strat.datas[0].datetime.array)
    equity_curve = [
        EquityPoint(timestamp=bt.num2date(dt), value=_safe_float(v))
        for dt, v in zip(dts_arr, values_arr)
    ]

    trades_list = [TradeInfo(**t) for t in strat.trade_log]

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
        cagr=cagr * 100,
        max_drawdown=max_dd,
        sharpe=sharpe,
        sortino=sortino,
        calmar=calmar,
        win_rate=win_rate,
        profit_factor=profit_factor,
        avg_win=avg_win,
        avg_loss=avg_loss,
        exposure=exposure,
        equity_curve=equity_curve,
        trades_list=trades_list,
    )
