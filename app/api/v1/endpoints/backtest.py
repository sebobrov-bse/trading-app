from fastapi import APIRouter, HTTPException
from starlette.concurrency import run_in_threadpool

from app.schemas.backtest import BacktestRequest, BacktestResult
from app.services.backtest_service import STRATEGY_REGISTRY, run_backtest

router = APIRouter(prefix="/backtest", tags=["backtest"])


@router.post("/run", response_model=BacktestResult)
async def run_backtest_endpoint(request: BacktestRequest) -> BacktestResult:
    """Run a backtest and return metrics.

    Backtrader is synchronous and CPU-bound, so we offload it to a thread
    pool. Otherwise one long-running backtest would block the event loop
    and freeze all other API requests.
    """
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