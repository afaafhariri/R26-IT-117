"""authdb connection: one async engine per app, short-lived sessions per request."""

from collections.abc import AsyncIterator
from datetime import UTC, datetime

from fastapi import Request
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker, create_async_engine


def utcnow() -> datetime:
    return datetime.now(UTC)


def create_engine(database_url: str) -> AsyncEngine:
    if not database_url:
        raise RuntimeError("DATABASE_URL is not set. See gateway/.env.example.")
    return create_async_engine(database_url, pool_pre_ping=True)


def make_sessionmaker(engine: AsyncEngine) -> async_sessionmaker[AsyncSession]:
    return async_sessionmaker(engine, expire_on_commit=False)


async def get_db(request: Request) -> AsyncIterator[AsyncSession]:
    """FastAPI dependency for the auth endpoints.

    Proxied requests don't use this: they would hold a pooled connection for
    the whole upstream call, which for C01 can be minutes.
    """
    async with request.app.state.db() as session:
        yield session
