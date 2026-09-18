"""Async PostgreSQL engine construction."""

from sqlalchemy.ext.asyncio import AsyncEngine, create_async_engine

from app.config import Settings


def build_engine(settings: Settings) -> AsyncEngine:
    """Create a PostgreSQL connection pool without opening a connection.

    The application owns the engine and must await dispose() during shutdown.
    Create one engine per process and use it within one event loop.
    """
    return create_async_engine(
        settings.database_url.get_secret_value(),
        echo=False,
        hide_parameters=True,
        pool_pre_ping=True,
        pool_size=5,
        max_overflow=5,
        pool_timeout=5,
        connect_args={
            "timeout": 5,
            "command_timeout": 15,
            "server_settings": {
                "timezone": "UTC",
            },
        },
    )
