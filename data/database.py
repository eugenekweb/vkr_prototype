"""
Инициализация подключения к БД через SQLAlchemy async.
Engine создаётся лениво при первом обращении к get_engine() —
это позволяет импортировать модуль без установленного asyncpg.
"""
import os
from typing import AsyncGenerator, Optional

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from data.models import Base

DATABASE_URL = os.getenv(
    "DATABASE_URL",
    "postgresql+asyncpg://tms_user:tms_pass@localhost:5432/tms",
)

_engine = None
_AsyncSessionFactory = None


def get_engine():
    global _engine
    if _engine is None:
        _engine = create_async_engine(DATABASE_URL, echo=False)
    return _engine


def AsyncSessionFactory():
    """Совместимость: вызывается как factory() для получения сессии."""
    global _AsyncSessionFactory
    if _AsyncSessionFactory is None:
        _AsyncSessionFactory = async_sessionmaker(get_engine(), expire_on_commit=False)
    return _AsyncSessionFactory()


async def get_session() -> AsyncGenerator[AsyncSession, None]:
    """FastAPI dependency: сессия на запрос."""
    async with AsyncSessionFactory() as session:
        async with session.begin():
            yield session


async def create_tables() -> None:
    """Создать таблицы (используется в тестах; в prod — Alembic)."""
    async with get_engine().begin() as conn:
        await conn.run_sync(Base.metadata.create_all)


async def drop_tables() -> None:
    """Удалить таблицы (используется в тестах)."""
    async with get_engine().begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)


# Обратная совместимость: engine как свойство модуля
class _EngineProxy:
    def __getattr__(self, name):
        return getattr(get_engine(), name)


engine = _EngineProxy()
