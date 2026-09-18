"""Run source synchronization as an explicit database command."""

import asyncio
import sys

from app.config import get_settings
from app.infrastructure.db.engine import build_engine
from app.infrastructure.db.repositories.source_seed import SourceSeedRepository
from app.infrastructure.db.session import build_session_factory, transaction_scope
from app.infrastructure.feeds.config import load_feed_configuration
from app.texts.feeds import FEEDS_SEED_FAILED, FEEDS_SEED_SUCCEEDED


async def run_seed() -> int:
    """Synchronize validated sources and release database resources.

    Configuration and provider exception details are excluded from CLI output.
    A failed synchronization rolls back the complete transaction.
    """
    try:
        settings = get_settings()
        configuration = load_feed_configuration(settings.feeds_config_path)
        engine = build_engine(settings)
    except Exception:
        # Configuration errors may contain sensitive connection metadata.
        print(FEEDS_SEED_FAILED, file=sys.stderr)
        return 1

    succeeded = False
    count = 0

    try:
        session_factory = build_session_factory(engine)

        async with transaction_scope(session_factory) as session:
            count = await SourceSeedRepository(session).synchronize(configuration)

        succeeded = True
    except Exception:
        # Database exception details must not appear in command output.
        print(FEEDS_SEED_FAILED, file=sys.stderr)
    finally:
        try:
            await engine.dispose()
        except Exception:
            if succeeded:
                print(FEEDS_SEED_FAILED, file=sys.stderr)
            succeeded = False

    if not succeeded:
        return 1

    print(FEEDS_SEED_SUCCEEDED.format(count=count))
    return 0


def main() -> int:
    """Execute source synchronization in a dedicated event loop."""
    return asyncio.run(run_seed())


if __name__ == "__main__":
    raise SystemExit(main())
