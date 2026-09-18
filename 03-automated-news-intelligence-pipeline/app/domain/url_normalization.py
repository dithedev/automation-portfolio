"""Canonical URL normalization for article deduplication."""

from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

from app.texts.feeds import URL_CANONICALIZE_FAILED, URL_SCHEME_UNSUPPORTED

_TRACKING_QUERY_EXACT = frozenset(
    {
        "gclid",
        "fbclid",
        "mc_cid",
        "mc_eid",
        "igshid",
        "_ga",
    }
)


def _is_tracking_param(name: str) -> bool:
    lowered = name.lower()
    return lowered.startswith("utm_") or lowered in _TRACKING_QUERY_EXACT


def canonicalize_url(value: str) -> str:
    """Normalize an HTTPS article URL for hashing and storage.

    Raises:
        ValueError: If the URL is not HTTPS or cannot be normalized.
    """
    raw = value.strip()
    if not raw:
        raise ValueError(URL_CANONICALIZE_FAILED)

    try:
        parsed = urlsplit(raw)
    except ValueError as error:
        raise ValueError(URL_CANONICALIZE_FAILED) from error

    scheme = parsed.scheme.lower()
    if scheme != "https":
        raise ValueError(URL_SCHEME_UNSUPPORTED)

    if parsed.username is not None or parsed.password is not None:
        raise ValueError(URL_CANONICALIZE_FAILED)

    hostname = parsed.hostname
    if hostname is None or not hostname.strip():
        raise ValueError(URL_CANONICALIZE_FAILED)

    try:
        ascii_host = hostname.strip().rstrip(".").encode("idna").decode("ascii").lower()
    except UnicodeError as error:
        raise ValueError(URL_CANONICALIZE_FAILED) from error

    netloc = f"{ascii_host}:{parsed.port}" if parsed.port not in (None, 443) else ascii_host

    path = parsed.path or "/"

    query_pairs = [
        (key, value)
        for key, value in parse_qsl(parsed.query, keep_blank_values=True)
        if not _is_tracking_param(key)
    ]
    query_pairs.sort(key=lambda item: (item[0], item[1]))
    query = urlencode(query_pairs, doseq=True)

    return urlunsplit((scheme, netloc, path if path else "/", query, ""))
