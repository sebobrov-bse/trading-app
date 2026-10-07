"""Backtest endpoints: run, history, details, delete."""

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import func, select
from sqlalchemy.orm import Session
from starlette.concurrency import run_in_threadpool

from app.db.session import get_db
from app.models.backtest import Backtest
from app.models.backtest_equity import BacktestEquity
from app.models.backtest_trade import BacktestTrade
from app.schemas.backtest import (
    BacktestDetails,
    BacktestHistoryItem,
    BacktestHistoryResponse,
    BacktestRequest,
    BacktestResult,
    CompareResponse,
    EquityPoint,
    TopStrategyItem,
    TradeInfo,
)
from app.services.backtest_service import (
    STRATEGY_REGISTRY,
    compare_backtests,
    run_backtest,
)


def parse_ids(ids: str) -> list[int]:
    """Parse comma-separated ids into a list of ints.

    Raises HTTPException(400) on invalid input.
    """
    try:
        result = [int(x.strip()) for x in ids.split(",") if x.strip()]
    except ValueError:
        raise HTTPException(
            status_code=400,
            detail="ids must be comma-separated integers",
        )
    if len(result) < 2:
        raise HTTPException(status_code=400, detail="at least 2 ids required")
    if len(result) > 5:
        raise HTTPException(status_code=400, detail="at most 5 ids allowed")
    return result


router = APIRouter(prefix="/backtest", tags=["backtest"])


@router.post("/run", response_model=BacktestResult)
async def run_backtest_endpoint(request: BacktestRequest) -> BacktestResult:
    """Run a backtest and persist the result to DB."""
    from app.services.backtest_service import get_strategy_class

    try:
        get_strategy_class(request.strategy)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))

    try:
        return await run_in_threadpool(run_backtest, request)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))


@router.get("/top-strategies", response_model=list[TopStrategyItem])
def top_strategies(
    limit: int = Query(3, ge=1, le=20),
    db: Session = Depends(get_db),
) -> list[TopStrategyItem]:
    """Aggregate backtests by strategy, sorted by average Sharpe."""
    stmt = (
        select(
            Backtest.strategy.label("strategy"),
            func.count(Backtest.id).label("count"),
            func.avg(Backtest.sharpe).label("avg_sharpe"),
            func.avg(Backtest.pnl).label("avg_pnl"),
            func.avg(Backtest.max_drawdown).label("avg_max_drawdown"),
        )
        .group_by(Backtest.strategy)
        .order_by(func.avg(Backtest.sharpe).desc())
        .limit(limit)
    )
    rows = db.execute(stmt).all()

    return [
        TopStrategyItem(
            strategy=r.strategy,
            count=r.count,
            avg_sharpe=float(r.avg_sharpe or 0),
            avg_pnl=float(r.avg_pnl or 0),
            avg_max_drawdown=float(r.avg_max_drawdown or 0),
        )
        for r in rows
    ]


@router.get("/history", response_model=BacktestHistoryResponse)
def backtest_history(
    symbol: str | None = Query(None, min_length=2, max_length=20),
    strategy: str | None = Query(None, min_length=1, max_length=50),
    limit: int = Query(50, ge=1, le=500),
    offset: int = Query(0, ge=0),
    db: Session = Depends(get_db),
) -> BacktestHistoryResponse:
    """List past backtest runs, newest first."""
    filters = []
    if symbol:
        filters.append(Backtest.symbol == symbol.upper())
    if strategy:
        filters.append(Backtest.strategy == strategy)

    count_stmt = select(func.count(Backtest.id)).where(*filters)
    total = db.execute(count_stmt).scalar_one()

    stmt = (
        select(Backtest)
        .where(*filters)
        .order_by(Backtest.created_at.desc(), Backtest.id.desc())
        .limit(limit)
        .offset(offset)
    )
    rows = db.execute(stmt).scalars().all()

    return BacktestHistoryResponse(
        items=[BacktestHistoryItem.model_validate(r) for r in rows],
        total=total,
        limit=limit,
        offset=offset,
    )


@router.get("/compare", response_model=CompareResponse)
def compare(
    ids: str = Query(..., description="Comma-separated backtest ids (2-5)"),
) -> CompareResponse:
    """Compare multiple backtests side by side."""
    parsed = parse_ids(ids)
    try:
        return compare_backtests(parsed)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc))


@router.get("/{backtest_id}", response_model=BacktestDetails)
def backtest_details(
    backtest_id: int,
    db: Session = Depends(get_db),
) -> BacktestDetails:
    """Return full details of one backtest with trades and equity."""
    bt_row = db.get(Backtest, backtest_id)
    if bt_row is None:
        raise HTTPException(status_code=404, detail="Backtest not found")

    trades = (
        db.execute(
            select(BacktestTrade)
            .where(BacktestTrade.backtest_id == backtest_id)
            .order_by(BacktestTrade.entry_time)
        )
        .scalars()
        .all()
    )

    equity = (
        db.execute(
            select(BacktestEquity)
            .where(BacktestEquity.backtest_id == backtest_id)
            .order_by(BacktestEquity.timestamp)
        )
        .scalars()
        .all()
    )

    details = BacktestDetails.model_validate(bt_row)
    details.trades_list = [
        TradeInfo(
            entry_time=t.entry_time,
            exit_time=t.exit_time,
            entry_price=float(t.entry_price),
            exit_price=float(t.exit_price),
            size=float(t.size),
            bars_held=t.bars_held,
            pnl=float(t.pnl),
            pnl_net=float(t.pnl_net),
            pnl_percent=float(t.pnl_percent),
        )
        for t in trades
    ]
    details.equity_curve = [
        EquityPoint(timestamp=e.timestamp, value=float(e.value)) for e in equity
    ]
    return details


@router.delete("/{backtest_id}", status_code=204)
def delete_backtest(
    backtest_id: int,
    db: Session = Depends(get_db),
) -> None:
    """Delete a backtest and all its trades/equity (cascade)."""
    bt_row = db.get(Backtest, backtest_id)
    if bt_row is None:
        raise HTTPException(status_code=404, detail="Backtest not found")
    db.delete(bt_row)
    db.commit()
