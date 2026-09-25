from fastapi import Depends, FastAPI
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.config import settings
from app.db.session import get_db
from app.models.system_status import SystemStatus


app = FastAPI(
    title=settings.app_name,
    version="0.1.0",
    debug=settings.debug,
)


@app.get("/health")
def health() -> dict[str, str]:
    """Health check endpoint."""
    return {"status": "ok"}


@app.get("/db-check")
def db_check(db: Session = Depends(get_db)) -> dict[str, str | int]:
    """Write a record to DB and return the latest one."""
    record = SystemStatus(status="ok")
    db.add(record)
    db.commit()
    db.refresh(record)

    stmt = select(SystemStatus).order_by(SystemStatus.id.desc()).limit(1)
    latest = db.execute(stmt).scalar_one()

    return {
        "id": latest.id,
        "status": latest.status,
        "created_at": latest.created_at.isoformat(),
    }