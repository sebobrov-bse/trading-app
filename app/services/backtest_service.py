"""Backtest service: load data, run a strategy, persist, return metrics."""

import logging
import math
from datetime import date, datetime
from decimal import Decimal
from typing import Any

import backtrader as bt
import numpy as np
from sqlalchemy import select


from app.backtest.feed import df_to_bt_feed
from app.db.session import SessionLocal
from app.models.backtest import Backtest
from app.models.backtest_equity import BacktestEquity
from app.models.backtest_trade import BacktestTrade
from app.schemas.backtest import (
    BacktestForCompare,
    BacktestMetrics,
    BacktestRequest,
    BacktestResult,
    CommonPeriod,
    CompareResponse,
    EquityPoint,
    TradeInfo,
)
from app.services.candle_repository import CandleRepository
from app.strategies.sma_crossover import SmaCrossover
from app.strategies.loader import load_builtin, load_custom

from app.risk.config import RiskConfig

logger = logging.getLogger(__name__)

STRATEGY_REGISTRY: dict[str, type[bt.Strategy]] = {
    "sma_crossover": SmaCrossover,
}


def get_strategy_class(name: str) -> type[bt.Strategy]:
    """Resolve a strategy name to a compiled Backtrader class.

    Resolution order:
    1. Static Python classes (STRATEGY_REGISTRY).
    2. `custom_<id>` — load from DB and compile.
    3. Builtin YAML configs (loaded once, cached).

    Raises ValueError if nothing matches.
    """
    if name in STRATEGY_REGISTRY:
        return STRATEGY_REGISTRY[name]

    if name.startswith("custom_"):
        try:
            sid = int(name.split("_", 1)[1])
        except (ValueError, IndexError):
            raise ValueError(f"Invalid custom strategy name: {name!r}")
        return load_custom(sid)

    builtin = load_builtin()
    if name in builtin:
        return builtin[name]

    available = sorted(set(STRATEGY_REGISTRY) | set(builtin) | {"custom_<id>"})
    raise ValueError(f"Unknown strategy '{name}'. Available: {available}")


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
        id=None,
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
        # Risk metrics
        avg_risk_per_trade=0.0,
        avg_rr_realized=0.0,
        avg_position_size_pct=0.0,
        stops_hit=0,
        take_profits_hit=0,
        max_consecutive_losses=0,
        skipped_by_atr=0,
        skipped_by_daily_limit=0,
    )


def _compute_sortino(returns: list[float]) -> float:
    """Annualized Sortino ratio from per-bar returns."""
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


def _persist_result(request: BacktestRequest, result: BacktestResult) -> int:
    """Save a Backtest with its trades and equity. Returns the new id."""
    with SessionLocal() as db:
        bt_row = Backtest(
            symbol=result.symbol,
            timeframe=result.timeframe,
            start_date=datetime.combine(result.start, datetime.min.time()),
            end_date=datetime.combine(result.end, datetime.min.time()),
            strategy=result.strategy,
            params=result.params,
            cash=Decimal(str(request.cash)),
            commission=Decimal(str(request.commission)),
            bars=result.bars,
            trades_count=result.trades,
            final_value=Decimal(str(result.final_value)),
            pnl=Decimal(str(result.pnl)),
            pnl_percent=Decimal(str(result.pnl_percent)),
            cagr=Decimal(str(result.cagr)),
            sharpe=Decimal(str(result.sharpe)),
            sortino=Decimal(str(result.sortino)),
            calmar=Decimal(str(result.calmar)),
            max_drawdown=Decimal(str(result.max_drawdown)),
            win_rate=Decimal(str(result.win_rate)),
            profit_factor=Decimal(str(result.profit_factor)),
            avg_win=Decimal(str(result.avg_win)),
            avg_loss=Decimal(str(result.avg_loss)),
            exposure=Decimal(str(result.exposure)),
        )
        db.add(bt_row)
        db.flush()  # get bt_row.id before creating related rows

        for t in result.trades_list:
            db.add(
                BacktestTrade(
                    backtest_id=bt_row.id,
                    entry_time=t.entry_time,
                    exit_time=t.exit_time,
                    entry_price=Decimal(str(t.entry_price)),
                    exit_price=Decimal(str(t.exit_price)),
                    size=Decimal(str(t.size)),
                    bars_held=t.bars_held,
                    pnl=Decimal(str(t.pnl)),
                    pnl_net=Decimal(str(t.pnl_net)),
                    pnl_percent=Decimal(str(t.pnl_percent)),
                )
            )

        for p in result.equity_curve:
            db.add(
                BacktestEquity(
                    backtest_id=bt_row.id,
                    timestamp=p.timestamp,
                    value=Decimal(str(p.value)),
                )
            )

        db.commit()
        return bt_row.id


def run_backtest(request: BacktestRequest) -> BacktestResult:
    """Load candles, run the strategy, persist, return extended metrics."""
    strategy_class = get_strategy_class(request.strategy)

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

    # Pass risk config to the strategy (or None → default RiskConfig).
    strategy_kwargs = dict(params)

    # Risk config resolution:
    # 1. request.risk_config — explicit override from client.
    # 2. strategy_class.default_risk_config — per-strategy default.
    # 3. RiskConfig() — global fallback.
    if request.risk_config is not None:
        strategy_kwargs["risk_config"] = request.risk_config
    else:
        default_risk = getattr(strategy_class, "default_risk_config", None)
        if default_risk:
            strategy_kwargs["risk_config"] = RiskConfig.model_validate(default_risk)

    cerebro.addstrategy(strategy_class, **strategy_kwargs)
    cerebro.broker.setcash(request.cash)
    cerebro.broker.setcommission(commission=request.commission)
    cerebro.addsizer(bt.sizers.PercentSizer, percents=95)

    cerebro.addobserver(bt.observers.Value)
    cerebro.addanalyzer(bt.analyzers.TradeAnalyzer, _name="trades")
    cerebro.addanalyzer(bt.analyzers.DrawDown, _name="dd")
    cerebro.addanalyzer(bt.analyzers.TimeReturn, _name="returns", timeframe=bt.TimeFrame.Days)
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

    won_pnl_total = _safe_float(ta.get("won", {}).get("pnl", {}).get("total", 0.0))
    lost_pnl_total = _safe_float(ta.get("lost", {}).get("pnl", {}).get("total", 0.0))
    avg_win = _safe_float(ta.get("won", {}).get("pnl", {}).get("average", 0.0))
    avg_loss = _safe_float(ta.get("lost", {}).get("pnl", {}).get("average", 0.0))

    gross_loss = abs(lost_pnl_total)
    profit_factor = (won_pnl_total / gross_loss) if gross_loss > 0 else 0.0
    win_rate = (won / total) if total else 0.0

    max_dd = _safe_float(dd.get("max", {}).get("drawdown", 0.0))
    sharpe = _safe_float(sharpe_an.get("sharperatio"))

    returns_list = [float(v) for v in returns_an.values()]
    sortino = _compute_sortino(returns_list)

    cagr = _compute_cagr(start_value, final_value, request.start, request.end)
    calmar = (cagr / (max_dd / 100.0)) if max_dd > 0 else 0.0
    exposure = strat.bars_in_market / len(strat) if len(strat) > 0 else 0.0

    values_arr = list(strat.observers.value.lines.value.array)
    dts_arr = list(strat.datas[0].datetime.array)
    equity_curve = [
        EquityPoint(timestamp=bt.num2date(dt), value=_safe_float(v))
        for dt, v in zip(dts_arr, values_arr)
    ]

    trades_list = [TradeInfo(**t) for t in strat.trade_log]

    # Extract risk stats from the strategy (if any).

    risk_stats: dict = {}
    if hasattr(strat, "risk") and strat.risk is not None:
        risk_stats = strat.risk.get_stats()

    result = BacktestResult(
        id=None,
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
        avg_risk_per_trade=risk_stats.get("avg_risk_per_trade", 0.0),
        avg_rr_realized=risk_stats.get("avg_rr_realized", 0.0),
        avg_position_size_pct=risk_stats.get("avg_position_size_pct", 0.0),
        stops_hit=risk_stats.get("stops_hit", 0),
        take_profits_hit=risk_stats.get("take_profits_hit", 0),
        max_consecutive_losses=risk_stats.get("max_consecutive_losses", 0),
        skipped_by_atr=risk_stats.get("skipped_by_atr", 0),
        skipped_by_daily_limit=risk_stats.get("skipped_by_daily_limit", 0),
    )

    # Persist the run to DB and attach its id.
    result.id = _persist_result(request, result)
    return result


def compare_backtests(ids: list[int]) -> CompareResponse:
    """Load backtests with metrics and equity curves for comparison.

    Uses exactly two queries (no N+1):
    - one for backtests,
    - one for all equity points across requested ids.

    Raises ValueError if some ids are not found.
    """
    with SessionLocal() as db:
        # Query 1: all backtests in one shot.
        bt_stmt = select(Backtest).where(Backtest.id.in_(ids))
        rows = db.execute(bt_stmt).scalars().all()

        found_ids = {r.id for r in rows}
        missing = [i for i in ids if i not in found_ids]
        if missing:
            raise ValueError(f"Backtests not found: {missing}")

        # Query 2: all equity points for all requested ids.
        eq_stmt = (
            select(BacktestEquity)
            .where(BacktestEquity.backtest_id.in_(ids))
            .order_by(BacktestEquity.backtest_id, BacktestEquity.timestamp)
        )
        equity_rows = db.execute(eq_stmt).scalars().all()

    # Group equity by backtest_id (in Python).
    equity_by_bt: dict[int, list[EquityPoint]] = {i: [] for i in ids}
    for e in equity_rows:
        equity_by_bt[e.backtest_id].append(EquityPoint(timestamp=e.timestamp, value=float(e.value)))

    # Preserve the order the user asked for.
    by_id = {r.id: r for r in rows}
    backtests = [
        BacktestForCompare(
            id=bt.id,
            symbol=bt.symbol,
            timeframe=bt.timeframe,
            start=bt.start_date.date(),
            end=bt.end_date.date(),
            strategy=bt.strategy,
            params=bt.params,
            metrics=BacktestMetrics(
                pnl=float(bt.pnl),
                pnl_percent=float(bt.pnl_percent),
                cagr=float(bt.cagr),
                sharpe=float(bt.sharpe),
                sortino=float(bt.sortino),
                calmar=float(bt.calmar),
                max_drawdown=float(bt.max_drawdown),
                win_rate=float(bt.win_rate),
                profit_factor=float(bt.profit_factor),
                trades_count=bt.trades_count,
            ),
            equity_curve=equity_by_bt[bt.id],
        )
        for bt in (by_id[i] for i in ids)
    ]

    common_start = max(b.start for b in backtests)
    common_end = min(b.end for b in backtests)

    return CompareResponse(
        backtests=backtests,
        common_period=CommonPeriod(start=common_start, end=common_end),
    )
