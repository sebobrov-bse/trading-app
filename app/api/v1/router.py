from fastapi import APIRouter

from app.api.v1.endpoints import (
    backtest,
    candles,
    custom_strategies,
    data,
    db_check,
    health,
    strategies,
)

api_v1_router = APIRouter(prefix="/api/v1")

api_v1_router.include_router(health.router)
api_v1_router.include_router(db_check.router)
api_v1_router.include_router(candles.router)
api_v1_router.include_router(backtest.router)
api_v1_router.include_router(data.router)
api_v1_router.include_router(custom_strategies.router)
api_v1_router.include_router(strategies.router)
