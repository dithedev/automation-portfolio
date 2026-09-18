"""Render an HTML digest body for persistence and later Telegram delivery."""

from __future__ import annotations

import html
from dataclasses import dataclass

from app.domain import DigestItem, NewsItem, Source
from app.texts.digest_format import (
    DIGEST_FOOTER_STORIES,
    DIGEST_FOOTER_VERIFY,
    DIGEST_ITEM_SEPARATOR,
    DIGEST_LINK_EMOJI,
    DIGEST_READ_ON_PREFIX,
    DIGEST_TAG_EMOJI,
    DIGEST_TITLE_EMOJI,
)

TELEGRAM_MESSAGE_LIMIT = 4096


@dataclass(frozen=True, slots=True, kw_only=True)
class RenderedDigestLine:
    item: DigestItem
    news_item: NewsItem
    source: Source


class DigestSplitError(ValueError):
    """Raised when a digest cannot be split into Telegram-safe parts."""


def _format_title(title: str) -> str:
    return f"{DIGEST_TITLE_EMOJI} <b>{html.escape(title.strip())}</b>"


def _item_block(line: RenderedDigestLine) -> str:
    article_title = html.escape(line.news_item.title)
    tag = html.escape(line.item.tag)
    summary = html.escape(line.item.summary)
    source_name = html.escape(line.source.name)
    href = html.escape(line.news_item.canonical_url, quote=True)
    return "\n".join(
        (
            f"<b>{line.item.position}. {article_title}</b>",
            f"<blockquote>{DIGEST_TAG_EMOJI} {tag}</blockquote>",
            summary,
            (f'{DIGEST_LINK_EMOJI} <a href="{href}">{DIGEST_READ_ON_PREFIX}{source_name}</a>'),
        )
    )


def _footer(count: int) -> str:
    return "\n".join(
        (
            DIGEST_FOOTER_STORIES.format(count=count),
            DIGEST_FOOTER_VERIFY,
        )
    )


def compose_digest_part(
    *,
    title: str | None,
    item_blocks: tuple[str, ...],
    footer: str | None,
) -> str:
    """Assemble one Telegram message body from optional title, items, and footer."""
    pieces: list[str] = []

    if title is not None:
        pieces.append(title.strip())

    if item_blocks:
        pieces.append(DIGEST_ITEM_SEPARATOR.join(item_blocks))

    if footer is not None:
        pieces.append(footer)

    return "\n\n".join(pieces).strip() + "\n"


def split_digest_messages(
    *,
    title: str,
    lines: tuple[RenderedDigestLine, ...],
    limit: int = TELEGRAM_MESSAGE_LIMIT,
) -> tuple[str, ...]:
    """Split digest text into Telegram parts at item boundaries only.

    Title appears on the first part; footer on the last. Packing reserves
    space for both so no part exceeds ``limit``. A single item that cannot
    fit with title and footer raises :class:`DigestSplitError`.
    """
    if not lines:
        raise DigestSplitError("digest must contain at least one item")

    formatted_title = _format_title(title)
    footer = _footer(len(lines))
    blocks = tuple(_item_block(line) for line in lines)

    for block in blocks:
        probe = compose_digest_part(
            title=formatted_title,
            item_blocks=(block,),
            footer=footer,
        )
        if len(probe) > limit:
            raise DigestSplitError(
                "a single digest item exceeds the Telegram message size limit",
            )

    groups: list[list[str]] = [[]]
    for block in blocks:
        candidate = [*groups[-1], block]
        probe = compose_digest_part(
            title=formatted_title,
            item_blocks=tuple(candidate),
            footer=footer,
        )
        if len(probe) <= limit:
            groups[-1] = candidate
            continue
        groups.append([block])

    parts: list[str] = []
    for index, group in enumerate(groups):
        is_first = index == 0
        is_last = index == len(groups) - 1
        part = compose_digest_part(
            title=formatted_title if is_first else None,
            item_blocks=tuple(group),
            footer=footer if is_last else None,
        )
        if len(part) > limit:
            raise DigestSplitError(
                "digest part exceeds the Telegram message size limit",
            )
        parts.append(part)

    return tuple(parts)


def render_digest_text(
    *,
    title: str,
    lines: tuple[RenderedDigestLine, ...],
) -> str:
    """Build the full HTML digest text without Telegram client calls."""
    return compose_digest_part(
        title=_format_title(title),
        item_blocks=tuple(_item_block(line) for line in lines),
        footer=_footer(len(lines)),
    )
