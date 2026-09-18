"""Async session construction and transaction boundaries."""

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker


def build_session_factory(
    engine: AsyncEngine,
) -> async_sessionmaker[AsyncSession]:
    """Create a factory that provides an independent session per operation.

    Loaded attributes remain available after commit. Relationships that
    require database access must still be loaded explicitly.
    """
    return async_sessionmaker(
        bind=engine,
        class_=AsyncSession,
        expire_on_commit=False,
        autoflush=False,
    )


@asynccontextmanager
async def transaction_scope(
    session_factory: async_sessionmaker[AsyncSession],
) -> AsyncIterator[AsyncSession]:
    """Open a session and commit or roll back one database transaction.

    Exceptions propagate after rollback, and the session is always closed.
    Keep external HTTP calls outside this scope. Callers must not commit,
    roll back, or close the session manually inside the scope.
    """
    async with session_factory.begin() as session:
        yield session
