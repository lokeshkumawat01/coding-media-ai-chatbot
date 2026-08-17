"""
Async SQLAlchemy engine and session setup for PostgreSQL.
All models inherit from `Base`. Use `get_db` as a FastAPI dependency
to get a session inside route handlers.
"""

from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession, async_sessionmaker
from sqlalchemy.orm import DeclarativeBase

from app.config import settings

engine = create_async_engine(
    settings.database_url,
    echo=settings.app_debug,
    pool_pre_ping=True,
)

AsyncSessionLocal = async_sessionmaker(
    bind=engine,
    class_=AsyncSession,
    expire_on_commit=False,
)


class Base(DeclarativeBase):
    """Base class for all ORM models."""

    pass


async def get_db():
    """
    FastAPI dependency that yields an async DB session
    and ensures it's closed after the request.
    """
    async with AsyncSessionLocal() as session:
        yield session
