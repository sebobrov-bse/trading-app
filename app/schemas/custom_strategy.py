"""Pydantic schemas for CustomStrategy CRUD API."""

from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class CustomStrategyCreate(BaseModel):
    """Request body for creating a custom strategy."""

    name: str = Field(..., min_length=1, max_length=100)
    description: str = ""
    config: dict[str, Any]


class CustomStrategyUpdate(BaseModel):
    """Request body for updating a custom strategy."""

    name: str | None = Field(None, min_length=1, max_length=100)
    description: str | None = None
    config: dict[str, Any] | None = None


class CustomStrategyRead(BaseModel):
    """Full custom strategy (with config)."""

    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str
    description: str
    config: dict[str, Any]
    created_at: datetime
    updated_at: datetime


class CustomStrategyListItem(BaseModel):
    """Short info for the list endpoint (no config)."""

    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str
    description: str
    created_at: datetime
    updated_at: datetime


class CustomStrategyListResponse(BaseModel):
    """List of custom strategies."""

    items: list[CustomStrategyListItem]
    total: int


class CustomStrategyImport(BaseModel):
    """Request body for YAML import."""

    yaml_content: str = Field(..., min_length=1)
