from datetime import datetime

from fastapi import APIRouter, HTTPException

from app.backtest.engine import run_backtest
from app.schemas.backtest import BacktestRequest, BacktestResponse
from app.services.candle_repository import CandleRepository

router = APIRouter(prefix="/backtest", tags=["backtest"])


def _parse_date(value: str | None) -> datetime | None:
    if value is None:
        return None
    try:
        return datetime.strptime(value, "%Y-%m-%d")
    except ValueError:
        raise HTTPException(
            status_code=422,
            detail=f"Invalid date '{value}'. Expected YYYY-MM-DD.",
        )


@router.post("", response_model=BacktestResponse)
def run_backtest_endpoint(payload: BacktestRequest) -> BacktestResponse:
    """Run a backtest on stored candles and return metrics."""
    if payload.fast >= payload.slow:
        raise HTTPException(
            status_code=422,
            detail="fast must be less than slow.",
        )

    repo = CandleRepository()
    df = repo.get_dataframe(
        symbol=payload.symbol,
        timeframe=payload.timeframe,
        start=_parse_date(payload.start),
        end=_parse_date(payload.end),
    )

    if df.empty:
        raise HTTPException(
            status_code=404,
            detail=f"No candles found for {payload.symbol} tf={payload.timeframe}.",
        )

    result = run_backtest(
        df,
        cash=payload.cash,
        commission=payload.commission,
        fast=payload.fast,
        slow=payload.slow,
    )

    return BacktestResponse(
        symbol=payload.symbol,
        timeframe=payload.timeframe,
        start_value=result.start_value,
        final_value=result.final_value,
        total_return_pct=result.total_return_pct,
        max_drawdown_pct=result.max_drawdown_pct,
        sharpe_ratio=result.sharpe_ratio,
        total_trades=result.total_trades,
        won_trades=result.won_trades,
        lost_trades=result.lost_trades,
        win_rate_pct=result.win_rate_pct,
    )