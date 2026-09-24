from contextlib import asynccontextmanager

from fastapi import Depends, FastAPI
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.config import settings
from app.db.base import Base
from app.db.session import engine, get_db
from app.models.system_status import SystemStatus


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Действия при старте и остановке приложения.

    Временно: создаём все таблицы через Base.metadata.create_all().
    В production это делает Alembic-миграция — create_all() не умеет
    изменять существующие таблицы и не хранит историю версий.
    """
    Base.metadata.create_all(bind=engine)
    yield


app = FastAPI(
    title=settings.app_name,
    version="0.1.0",
    debug=settings.debug,
    lifespan=lifespan,
)


@app.get("/health")
def health() -> dict[str, str]:
    """Проверка живости приложения."""
    return {"status": "ok"}


@app.get("/db-check")
def db_check(db: Session = Depends(get_db)) -> dict[str, str | int]:
    """Пишет запись в БД и возвращает последнюю.

    Проверяет: подключение, запись, чтение, закрытие сессии.
    """
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