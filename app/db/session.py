from collections.abc import Generator

from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

from app.config import settings

# Движок — точка подключения к БД. Для SQLite указываем check_same_thread=False,
# потому что FastAPI обрабатывает sync-эндпоинты в пуле потоков, а SQLite
# по умолчанию запрещает доступ из разных потоков.
engine = create_engine(
    settings.database_url,
    echo=settings.debug,
    connect_args={"check_same_thread": False}
    if settings.database_url.startswith("sqlite")
    else {},
)

# Фабрика сессий. autoflush=False — не отправлять изменения в БД до commit.
# expire_on_commit=False — не «забывать» объекты после commit, чтобы можно было
# читать их поля в ответе эндпоинта.
SessionLocal = sessionmaker(
    bind=engine,
    autoflush=False,
    autocommit=False,
    expire_on_commit=False,
)


def get_db() -> Generator[Session, None, None]:
    """FastAPI-зависимость: отдаёт сессию и закрывает её после запроса.

    Использование в эндпоинте:
        def my_endpoint(db: Session = Depends(get_db)): ...
    """
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()