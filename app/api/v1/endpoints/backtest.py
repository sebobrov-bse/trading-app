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
    EquityPoint,
    TradeInfo,
)
from app.services.backtest_service import STRATEGY_REGISTRY, run_backtest

router = APIRouter(prefix="/backtest", tags=["backtest"])


@router.post("/run", response_model=BacktestResult)
async def run_backtest_endpoint(request: BacktestRequest) -> BacktestResult:
    """Run a backtest and persist the result to DB."""
    if request.strategy not in STRATEGY_REGISTRY:
        raise HTTPException(
            status_code=400,
            detail=(
                f"Unknown strategy '{request.strategy}'. "
                f"Available: {sorted(STRATEGY_REGISTRY)}"
            ),
        )

    try:
        return await run_in_threadpool(run_backtest, request)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))


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


@router.get("/{backtest_id}", response_model=BacktestDetails)
def backtest_details(
    backtest_id: int,
    db: Session = Depends(get_db),
) -> BacktestDetails:
    """Return full details of one backtest with trades and equity."""
    bt_row = db.get(Backtest, backtest_id)
    if bt_row is None:
        raise HTTPException(status_code=404, detail="Backtest not found")

    trades = db.execute(
        select(BacktestTrade)
        .where(BacktestTrade.backtest_id == backtest_id)
        .order_by(BacktestTrade.entry_time)
    ).scalars().all()

    equity = db.execute(
        select(BacktestEquity)
        .where(BacktestEquity.backtest_id == backtest_id)
        .order_by(BacktestEquity.timestamp)
    ).scalars().all()

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