from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.models.system_status import SystemStatus
from app.schemas.health import DBCheckResponse

router = APIRouter(tags=["health"])


@router.get("/db-check", response_model=DBCheckResponse)
def db_check(db: Session = Depends(get_db)) -> DBCheckResponse:
    """Write a record to system_status and return the latest one."""
    record = SystemStatus(status="ok")
    db.add(record)
    db.commit()
    db.refresh(record)

    stmt = select(SystemStatus).order_by(SystemStatus.id.desc()).limit(1)
    latest = db.execute(stmt).scalar_one()

    return DBCheckResponse(
        id=latest.id,
        status=latest.status,
        created_at=latest.created_at,
    )