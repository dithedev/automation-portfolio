"""Tests for feed HTML sanitization."""

from app.domain.text_sanitize import normalize_title, sanitize_feed_text


def test_sanitize_strips_scripts_and_tags() -> None:
    raw = "<p>Hello<script>alert(1)</script><b>World</b></p>"

    assert sanitize_feed_text(raw, maximum_length=12_000) == "HelloWorld"


def test_sanitize_decodes_entities_and_collapses_whitespace() -> None:
    raw = "Alpha&nbsp;&amp;&nbsp;  Beta"

    assert sanitize_feed_text(raw, maximum_length=12_000) == "Alpha & Beta"


def test_sanitize_truncates_to_maximum_length() -> None:
    assert sanitize_feed_text("abcdefghij", maximum_length=5) == "abcde"


def test_normalize_title_lowercases_and_collapses() -> None:
    assert normalize_title("  Hello   WORLD  ") == "hello world"
