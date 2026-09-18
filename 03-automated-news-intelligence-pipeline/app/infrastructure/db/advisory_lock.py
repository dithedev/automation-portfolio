"""PostgreSQL session-level advisory lock for pipeline exclusivity."""

from __future__ import annotations

from types import TracebackType

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncConnection, AsyncEngine

# Stable application key for the daily digest pipeline lock.
PIPELINE_ADVISORY_LOCK_KEY = 0x4E495053_44494745  # "NIPS DIGE"


class PipelineAdvisoryLock:
    """Hold a session advisory lock on a dedicated database connection."""

    def __init__(
        self,
        engine: AsyncEngine,
        *,
        lock_key: int = PIPELINE_ADVISORY_LOCK_KEY,
    ) -> None:
        self._engine = engine
        self._lock_key = lock_key
        self._connection: AsyncConnection | None = None
        self._acquired = False

    @property
    def acquired(self) -> bool:
        return self._acquired

    async def acquire(self) -> bool:
        """Try to acquire the lock. Returns False when another holder exists."""
        if self._acquired:
            return True

        connection = await self._engine.connect()
        try:
            result = await connection.execute(
                text("SELECT pg_try_advisory_lock(:lock_key)"),
                {"lock_key": self._lock_key},
            )
            locked = bool(result.scalar_one())
            if not locked:
                await connection.close()
                return False

            self._connection = connection
            self._acquired = True
            return True
        except Exception:
            await connection.close()
            raise

    async def release(self) -> None:
        """Release the lock and close the dedicated connection."""
        connection = self._connection
        self._connection = None
        acquired = self._acquired
        self._acquired = False

        if connection is None:
            return

        try:
            if acquired:
                await connection.execute(
                    text("SELECT pg_advisory_unlock(:lock_key)"),
                    {"lock_key": self._lock_key},
                )
        finally:
            await connection.close()

    async def __aenter__(self) -> PipelineAdvisoryLock:
        await self.acquire()
        return self

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        traceback: TracebackType | None,
    ) -> None:
        await self.release()
