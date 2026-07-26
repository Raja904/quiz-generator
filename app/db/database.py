"""
app/db/database.py

SQLAlchemy async engine and session maker for Supabase PostgreSQL connection.
"""

from collections.abc import AsyncGenerator
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.orm import declarative_base

from app.core.config import settings

# If no DATABASE_URL is provided, we create a dummy engine for testing/fallback
# (Though in production, this should raise an error if not configured)
DB_URL = settings.database_url
if DB_URL:
    if DB_URL.startswith("postgres://"):
        DB_URL = DB_URL.replace("postgres://", "postgresql+asyncpg://", 1)
    elif DB_URL.startswith("postgresql://"):
        DB_URL = DB_URL.replace("postgresql://", "postgresql+asyncpg://", 1)
        
    # asyncpg doesn't support the pgbouncer=true query parameter, so we strip it.
    if "?pgbouncer=true" in DB_URL:
        DB_URL = DB_URL.replace("?pgbouncer=true", "")
    elif "&pgbouncer=true" in DB_URL:
        DB_URL = DB_URL.replace("&pgbouncer=true", "")
else:
    DB_URL = "sqlite+aiosqlite:///:memory:"

engine = create_async_engine(
    DB_URL,
    echo=settings.log_level.upper() == "DEBUG",
    future=True,
    pool_pre_ping=True,
    connect_args={"statement_cache_size": 0} if "asyncpg" in DB_URL else {},
)

async_session_maker = async_sessionmaker(
    engine, class_=AsyncSession, expire_on_commit=False
)

Base = declarative_base()


async def get_db() -> AsyncGenerator[AsyncSession, None]:
    """FastAPI dependency that provides an async database session."""
    async with async_session_maker() as session:
        yield session
