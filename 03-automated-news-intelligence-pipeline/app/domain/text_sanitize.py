"""Strip untrusted HTML from feed text before persistence."""

from html import unescape
from re import sub

import nh3


def sanitize_feed_text(value: str, *, maximum_length: int) -> str:
    """Remove markup, decode entities, collapse whitespace, and truncate."""
    cleaned = nh3.clean(value, tags=set(), attributes={})
    decoded = unescape(cleaned)
    collapsed = sub(r"\s+", " ", decoded).strip()

    if len(collapsed) <= maximum_length:
        return collapsed

    return collapsed[:maximum_length].rstrip()


def normalize_title(value: str) -> str:
    """Lowercase and collapse whitespace for title comparison."""
    collapsed = sub(r"\s+", " ", value).strip().lower()
    return collapsed
