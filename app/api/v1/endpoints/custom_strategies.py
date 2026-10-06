"""CRUD API for user-defined custom strategies."""

import json
import logging

import yaml
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.models.custom_strategy import CustomStrategy
from app.schemas.custom_strategy import (
    CustomStrategyCreate,
    CustomStrategyImport,
    CustomStrategyListItem,
    CustomStrategyListResponse,
    CustomStrategyRead,
    CustomStrategyUpdate,
)
from app.strategies.builder.config import StrategyConfig

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/strategies/custom", tags=["custom-strategies"])


def _validate_config(raw: dict) -> StrategyConfig:
    try:
        return StrategyConfig.model_validate(raw)
    except Exception as exc:
        raise HTTPException(
            status_code=422,
            detail=f"Invalid strategy config: {exc}",
        )


def _to_read(row: CustomStrategy) -> CustomStrategyRead:
    return CustomStrategyRead(
        id=row.id,
        name=row.name,
        description=row.description,
        config=json.loads(row.config_json),
        created_at=row.created_at,
        updated_at=row.updated_at,
    )


@router.post("", response_model=CustomStrategyRead, status_code=201)
def create_custom_strategy(
    payload: CustomStrategyCreate,
    db: Session = Depends(get_db),
) -> CustomStrategyRead:
    """Create a new custom strategy."""
    _validate_config(payload.config)

    existing = db.execute(
        select(CustomStrategy).where(CustomStrategy.name == payload.name)
    ).scalar_one_or_none()
    if existing is not None:
        raise HTTPException(
            status_code=409,
            detail=f"Strategy with name '{payload.name}' already exists",
        )

    row = CustomStrategy(
        name=payload.name,
        description=payload.description,
        config_json=json.dumps(payload.config),
    )
    db.add(row)
    db.commit()
    db.refresh(row)
    return _to_read(row)


@router.get("", response_model=CustomStrategyListResponse)
def list_custom_strategies(
    limit: int = Query(50, ge=1, le=500),
    offset: int = Query(0, ge=0),
    db: Session = Depends(get_db),
) -> CustomStrategyListResponse:
    """List custom strategies (newest first)."""
    total = db.execute(select(func.count(CustomStrategy.id))).scalar_one()

    rows = (
        db.execute(
            select(CustomStrategy)
            .order_by(CustomStrategy.updated_at.desc(), CustomStrategy.id.desc())
            .limit(limit)
            .offset(offset)
        )
        .scalars()
        .all()
    )

    return CustomStrategyListResponse(
        items=[CustomStrategyListItem.model_validate(r) for r in rows],
        total=total,
    )


@router.get("/{strategy_id}", response_model=CustomStrategyRead)
def get_custom_strategy(
    strategy_id: int,
    db: Session = Depends(get_db),
) -> CustomStrategyRead:
    """Get one custom strategy with its config."""
    row = db.get(CustomStrategy, strategy_id)
    if row is None:
        raise HTTPException(status_code=404, detail="Custom strategy not found")
    return _to_read(row)


@router.put("/{strategy_id}", response_model=CustomStrategyRead)
def update_custom_strategy(
    strategy_id: int,
    payload: CustomStrategyUpdate,
    db: Session = Depends(get_db),
) -> CustomStrategyRead:
    """Update a custom strategy."""
    row = db.get(CustomStrategy, strategy_id)
    if row is None:
        raise HTTPException(status_code=404, detail="Custom strategy not found")

    if payload.name is not None and payload.name != row.name:
        existing = db.execute(
            select(CustomStrategy).where(
                CustomStrategy.name == payload.name,
                CustomStrategy.id != strategy_id,
            )
        ).scalar_one_or_none()
        if existing is not None:
            raise HTTPException(
                status_code=409,
                detail=f"Strategy with name '{payload.name}' already exists",
            )
        row.name = payload.name

    if payload.description is not None:
        row.description = payload.description

    if payload.config is not None:
        _validate_config(payload.config)
        row.config_json = json.dumps(payload.config)

    db.commit()
    db.refresh(row)
    return _to_read(row)


@router.delete("/{strategy_id}", status_code=204)
def delete_custom_strategy(
    strategy_id: int,
    db: Session = Depends(get_db),
) -> None:
    """Delete a custom strategy."""
    row = db.get(CustomStrategy, strategy_id)
    if row is None:
        raise HTTPException(status_code=404, detail="Custom strategy not found")
    db.delete(row)
    db.commit()


@router.get("/{strategy_id}/export")
def export_yaml(
    strategy_id: int,
    db: Session = Depends(get_db),
) -> dict:
    """Export a custom strategy as YAML text."""
    row = db.get(CustomStrategy, strategy_id)
    if row is None:
        raise HTTPException(status_code=404, detail="Custom strategy not found")

    config = json.loads(row.config_json)
    yaml_text = yaml.safe_dump(config, sort_keys=False, allow_unicode=True)
    return {"id": row.id, "name": row.name, "yaml": yaml_text}


@router.post("/import", response_model=CustomStrategyRead, status_code=201)
def import_yaml(
    payload: CustomStrategyImport,
    db: Session = Depends(get_db),
) -> CustomStrategyRead:
    """Import a custom strategy from YAML text."""
    try:
        parsed = yaml.safe_load(payload.yaml_content)
    except yaml.YAMLError as exc:
        raise HTTPException(status_code=422, detail=f"Invalid YAML: {exc}")

    if not isinstance(parsed, dict):
        raise HTTPException(status_code=422, detail="YAML root must be a mapping")

    _validate_config(parsed)

    name = parsed.get("name")
    if not name:
        raise HTTPException(status_code=422, detail="YAML must contain a 'name' field")

    existing = db.execute(
        select(CustomStrategy).where(CustomStrategy.name == name)
    ).scalar_one_or_none()
    if existing is not None:
        raise HTTPException(
            status_code=409,
            detail=f"Strategy with name '{name}' already exists",
        )

    row = CustomStrategy(
        name=name,
        description=parsed.get("description", ""),
        config_json=json.dumps(parsed),
    )
    db.add(row)
    db.commit()
    db.refresh(row)
    return _to_read(row)
