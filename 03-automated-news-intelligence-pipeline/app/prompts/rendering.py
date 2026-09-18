"""Serialize article data for a separate model input message."""

import json
from collections.abc import Mapping, Sequence


def render_articles(articles: Sequence[Mapping[str, str]]) -> str:
    """Serialize articles as JSON without modifying generation instructions.

    Article values are never interpolated into system or repair prompts.
    JSON serialization separates data from instructions but does not guarantee
    protection against prompt injection. Generated output still requires
    schema validation and source-grounding checks.

    Raises:
        TypeError: If article data cannot be serialized as JSON.
    """
    return json.dumps(
        {"articles": [dict(article) for article in articles]},
        ensure_ascii=False,
        allow_nan=False,
    )
