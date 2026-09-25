from datetime import datetime

from pydantic import BaseModel


class HealthResponse(BaseModel):
    """Response for /health: app and DB status."""

    status: str
    database: str


class DBCheckResponse(BaseModel):
    """Response for /db-check: latest record from system_status."""

    id: int
    status: str
    created_at: datetime