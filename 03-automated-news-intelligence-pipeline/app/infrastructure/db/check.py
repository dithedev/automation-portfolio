"""Command-line database connectivity diagnostics."""

import asyncio
import sys

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncEngine

from app.config import get_settings
from app.infrastructure.db.engine import build_engine
from app.infrastructure.db.session import build_session_factory, transaction_scope
from app.texts.db import (
    DATABASE_CHECK_FAILED,
    DATABASE_CHECK_SUCCEEDED,
    DATABASE_CONFIGURATION_INVALID,
    DATABASE_PROBE_INVALID,
)


async def check_database(engine: AsyncEngine) -> None:
    """Verify direct connection access and session-based SQL execution.

    Raises:
        RuntimeError: If a probe returns an unexpected value.
        Exception: If PostgreSQL cannot be reached or a query fails.
    """
    async with engine.connect() as connection:
        result = await connection.scalar(select(1))

        if result != 1:
            raise RuntimeError(DATABASE_PROBE_INVALID)

    session_factory = build_session_factory(engine)

    async with transaction_scope(session_factory) as session:
        result = await session.scalar(select(1))

        if result != 1:
            raise RuntimeError(DATABASE_PROBE_INVALID)


async def run_check() -> int:
    """Run diagnostics and release the engine before returning an exit code."""
    try:
        engine = build_engine(get_settings())
    except Exception:
        # Configuration exceptions may contain sensitive connection metadata.
        print(DATABASE_CONFIGURATION_INVALID, file=sys.stderr)
        return 1

    succeeded = False

    try:
        await check_database(engine)
        succeeded = True
    except Exception:
        # Provider exception text is intentionally excluded from CLI output.
        print(DATABASE_CHECK_FAILED, file=sys.stderr)
    finally:
        try:
            await engine.dispose()
        except Exception:
            if succeeded:
                print(DATABASE_CHECK_FAILED, file=sys.stderr)
            succeeded = False

    if not succeeded:
        return 1

    print(DATABASE_CHECK_SUCCEEDED)
    return 0


def main() -> int:
    """Execute the database diagnostic command in a dedicated event loop."""
    return asyncio.run(run_check())


if __name__ == "__main__":
    raise SystemExit(main())
