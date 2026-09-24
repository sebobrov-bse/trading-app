from sqlalchemy.orm import DeclarativeBase


class Base(DeclarativeBase):
    """Базовый класс для всех ORM-моделей проекта.

    Все модели наследуются от него. SQLAlchemy собирает метаданные
    (таблицы, колонки, типы) в Base.metadata, что позволяет создавать
    таблицы одной командой и использовать Alembic для миграций.
    """