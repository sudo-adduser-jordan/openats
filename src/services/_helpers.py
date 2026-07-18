"""Shared helpers for ATS collectors.

Centralises the most duplicated utilities across the collector package:

* :func:`parse_iso_datetime` — ISO-8601 string → ``datetime`` (25 copies).
* :func:`strip_html` — HTML → plain text with block-tag preservation (~20 copies).
* :data:`TAG_RE` — compiled ``<[^>]+>`` regex shared across collectors.
* :func:`as_url` / :func:`as_url_or_none` — ``str`` → ``HttpUrl`` helpers.
"""

from __future__ import annotations

import html
import re
from datetime import datetime

from pydantic import HttpUrl

# Compiled regex for matching any HTML tag.  Used by :func:`strip_html` and
# available for callers that need partial tag handling.
TAG_RE = re.compile(r"<[^>]+>")

# Block-level closing / self-closing tags → newline *before* general strip
# so that list items, paragraphs, and headings don't collapse into a single
# space-separated blob.
_BLOCK_LEVEL_RE = re.compile(
    r"<\s*(?:br\s*/?|/li|/p|/div|/h[1-6]|/tr|/ul|/ol)\s*>",
    re.IGNORECASE,
)

# Horizontal whitespace only — preserves newlines so paragraph boundaries
# survive the clean.
_HORIZ_WS_RE = re.compile(r"[ \t\r\f\v]+")

# Squash 3+ consecutive newlines down to 2 (one blank line).
_BLANK_LINES_RE = re.compile(r"\n{3,}")


# ---------------------------------------------------------------------------
# datetime
# ---------------------------------------------------------------------------


def parse_iso_datetime(value: object) -> datetime | None:
    """Parse an ISO-8601 timestamp string into a timezone-aware ``datetime``.

    Handles the common ``"Z"`` suffix (replaced with ``"+00:00"`` before
    parsing).  Returns ``None`` when *value* is not a string, is empty /
    whitespace-only, or cannot be parsed — never raises.

    This is the single shared implementation replacing 22+ identical
    ``_parse_iso`` copies across collector modules.  Collectors that need
    additional fallback formats (bare dates, ``strptime`` patterns, etc.)
    should call this first and fall through to their local logic on
    ``None``.
    """
    if not isinstance(value, str) or not value.strip():
        return None
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None


# ---------------------------------------------------------------------------
# HTML → plain text
# ---------------------------------------------------------------------------


def strip_html(raw: str) -> str:
    """Convert an HTML string to plain text.

    Processing order:

    1. ``html.unescape`` — decode entities so encoded tags (``&lt;``)
       become real angle-brackets.
    2. Replace block-level tags with newlines — preserves paragraph /
       list structure.
    3. Strip remaining tags.
    4. Collapse horizontal whitespace; squash 3+ newlines.

    Callers should apply the ~25k char truncation *after* calling this
    function.  Collectors that intentionally keep HTML for a downstream
    ``markdownify`` pass should **not** use this helper.
    """
    text = html.unescape(raw)
    text = _BLOCK_LEVEL_RE.sub("\n", text)
    text = TAG_RE.sub("", text)
    text = _HORIZ_WS_RE.sub(" ", text)
    text = _BLANK_LINES_RE.sub("\n\n", text)
    return text.strip()


# ---------------------------------------------------------------------------
# URL helpers
# ---------------------------------------------------------------------------


def as_url(url: str) -> HttpUrl:
    """Convert a plain ``str`` to a Pydantic ``HttpUrl``.

    Avoids repeating ``HttpUrl(...)`` at every collector call site while
    keeping the type checker happy about ``Job(url=...)``.
    """
    return HttpUrl(url)


def as_url_or_none(url: str | None) -> HttpUrl | None:
    """Like :func:`as_url` but returns ``None`` for ``None`` inputs."""
    return HttpUrl(url) if url else None
