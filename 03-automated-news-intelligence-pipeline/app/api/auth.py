"""Admin API key checks for operational endpoints."""

from __future__ import annotations

import hmac

from app.config import Settings


def admin_api_key_is_valid(settings: Settings, provided: str | None) -> bool:
    """Return True when the provided key matches the configured admin secret."""
    expected = settings.admin_api_key
    if expected is None or provided is None:
        return False
    left = provided.encode("utf-8")
    right = expected.get_secret_value().encode("utf-8")
    if len(left) != len(right):
        return False
    return hmac.compare_digest(left, right)
