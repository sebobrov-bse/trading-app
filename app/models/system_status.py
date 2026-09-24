from datetime import datetime

from sqlalchemy import DateTime, Integer, String, func
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class SystemStatus(Base):
    """Тестовая таблица для проверки работы БД.

    Не несёт бизнес-смысла. Служит для проверки:
    - создания таблиц при старте,
    - записи и чтения через SQLAlchemy,
    - работы эндпоинта /db-check.
    """

    __tablename__ = "system_status"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    status: Mapped[str] = mapped_column(String(50), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now(), nullable=False
    )

    def __repr__(self) -> str:
        return f"<SystemStatus id={self.id} status={self.status!r}>"