"""Strategy metadata endpoints.

Unified API for all strategies (Python classes, builtin YAML, custom
from DB). Frontend uses this to build forms dynamically.
"""

import logging

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.schemas.strategy import StrategyListResponse, StrategyMetadata
from app.services.strategy_registry import (
    get_all_strategies,
    get_strategy_by_name,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/strategies", tags=["strategies"])


@router.get("", response_model=StrategyListResponse)
def list_strategies(
    db: Session = Depends(get_db),
) -> StrategyListResponse:
    """Return all strategies from all sources.

    Order: builtin, then custom, then python.
    Within each group — by display_name.
    """
    items = get_all_strategies(db)
    return StrategyListResponse(items=items, total=len(items))


@router.get("/{name}", response_model=StrategyMetadata)
def get_strategy(
    name: str,
    db: Session = Depends(get_db),
) -> StrategyMetadata:
    """Return one strategy by name.

    Accepts:
    - Python class name (e.g. "sma_crossover")
    - Builtin slug (e.g. "rsi_mean_reversion")
    - Custom by id (e.g. "custom_1")
    - Custom by display name (e.g. "RSI Simple")
    """
    metadata = get_strategy_by_name(db, name)
    if metadata is None:
        raise HTTPException(
            status_code=404,
            detail=f"Strategy '{name}' not found",
        )
    return metadata
