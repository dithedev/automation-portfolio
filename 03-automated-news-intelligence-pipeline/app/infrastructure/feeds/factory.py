"""Build the feed HTTP client for live network fetch or demo fixtures."""

from app.application.ports import FeedHttpClient
from app.config import Settings
from app.infrastructure.feeds.demo_client import DemoFixtureFeedHttpClient
from app.infrastructure.feeds.http import SafeFeedHttpClient


def build_feed_http_client(settings: Settings) -> FeedHttpClient:
    """Use local RSS fixtures in demo mode; otherwise the hardened HTTP client."""
    if settings.app_mode == "demo":
        return DemoFixtureFeedHttpClient(settings)
    return SafeFeedHttpClient(settings)
