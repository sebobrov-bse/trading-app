from fastapi import APIRouter, Depends
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.schemas.health import HealthResponse

router = APIRouter(tags=["health"])


@router.get("/health", response_model=HealthResponse)
def health(db: Session = Depends(get_db)) -> HealthResponse:
    """Check app liveness and DB availability.

    Runs SELECT 1 to verify the DB connection is alive.
    """
    try:
        db.execute(text("SELECT 1"))
        database = "ok"
    except Exception:
        database = "error"

    return HealthResponse(status="ok", database=database)