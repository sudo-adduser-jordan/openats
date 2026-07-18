"""Sitemap-based job discovery for openats.

Probes a careers URL for known sitemap paths, parses XML/RSS feeds,
and returns ``Job`` instances without needing an ATS-specific collector.

Usage::

    >>> from discovery import discover_jobs
    >>> jobs = discover_jobs("https://careers.example.com")
    >>> len(jobs)
    42

Or from the CLI::

    $ openats discover https://careers.example.com
"""

from __future__ import annotations

import sqlite3
import sys
from datetime import UTC, datetime
from typing import TYPE_CHECKING
from urllib.parse import urlparse
from xml.etree import ElementTree as ET

import httpx

from database.database import SELECT_COMPANY_URL_BY_SLUG_OR_NAME
from services._helpers import as_url, parse_iso_datetime
from services._models import ATSType, Job

if TYPE_CHECKING:
    pass

# ── Known sitemap paths probed in order ──────────────────────────────────

SITEMAP_PATHS = [
    "/sitemap.xml",
    "/sitemal.xml",
    "/sitemap_index.xml",
    "/sitemaps/sitemap.xml",
    "/sitemaps/jobs.xml",
    "/jobs/sitemap.xml",
    "/careers/sitemap.xml",
    "/sitemapindex.xml",
    "/sitemap/sitemap.xml",
    "/rss/feed.xml",
]

# ── XML namespaces ───────────────────────────────────────────────────────

NS_SITEMAP = "http://www.sitemaps.org/schemas/sitemap/0.9"

# ── Helpers ──────────────────────────────────────────────────────────────


def _host_from_url(url: str) -> str:
    return urlparse(url).hostname or url


def _company_name_from_url(url: str) -> str:
    """Derive a display name from a careers URL."""
    host = _host_from_url(url)
    # Strip common prefixes
    name = host.replace("www.", "").replace("careers.", "").replace("job.", "")
    # Take first dotted segment
    name = name.split(".")[0]
    # Title-case and clean
    return name.replace("-", " ").replace("_", " ").title().strip() or host


def _title_from_url(url: str) -> str:
    """Extract a readable job title from a URL path."""
    path = urlparse(url).path.rstrip("/")
    segment = path.rsplit("/", 1)[-1] if path else ""
    if not segment or segment in ("jobs", "careers", "job"):
        return "Untitled Position"
    # Decode URL-encoded chars and hyphens
    from urllib.parse import unquote

    title = unquote(segment.replace("-", " ").replace("_", " ").replace("+", " "))
    return title.strip().title() or "Untitled Position"


def _ats_id_from_url(url: str) -> str | None:
    """Derive an ATS identifier from a URL."""
    path = urlparse(url).path.rstrip("/")
    segment = path.rsplit("/", 1)[-1] if path else ""
    if segment and segment not in ("jobs", "careers", "job"):
        return segment
    return url


def _parse_lastmod(text: str | None) -> datetime | None:
    if not text or not text.strip():
        return None
    parsed = parse_iso_datetime(text.strip())
    if parsed:
        return parsed
    # Try date-only formats like "2026-07-13"
    try:
        from datetime import date

        d = date.fromisoformat(text.strip())
        return datetime(d.year, d.month, d.day, tzinfo=UTC)
    except (ValueError, TypeError):
        pass
    return None


# ── Sitemap parsing ──────────────────────────────────────────────────────


def _parse_urlset(xml: str) -> list[dict[str, str]]:
    """Parse a standard ``<urlset>`` sitemap.

    Returns a list of dicts with keys ``loc``, ``lastmod``, ``changefreq``,
    ``priority`` — only ``loc`` is guaranteed to be present.
    """
    root = ET.fromstring(xml)
    entries: list[dict[str, str]] = []
    # urlset with or without namespace
    ns = _detect_ns(root.tag)
    for url_elem in root.iter(f"{{{ns}}}url" if ns else "url"):
        loc = _find_text(url_elem, "loc", ns)
        if not loc:
            continue
        entries.append(
            {
                "loc": loc,
                "lastmod": _find_text(url_elem, "lastmod", ns) or "",
                "changefreq": _find_text(url_elem, "changefreq", ns) or "",
                "priority": _find_text(url_elem, "priority", ns) or "",
            }
        )
    return entries


def _parse_sitemapindex(xml: str) -> list[str]:
    """Parse a ``<sitemapindex>`` and return sub-sitemap URLs."""
    root = ET.fromstring(xml)
    ns = _detect_ns(root.tag)
    urls: list[str] = []
    for sm in root.iter(f"{{{ns}}}sitemap" if ns else "sitemap"):
        loc = _find_text(sm, "loc", ns)
        if loc:
            urls.append(loc)
    return urls


def _parse_rss(xml: str) -> list[dict[str, str]]:
    """Parse an RSS 2.0 feed into a list of item dicts."""
    root = ET.fromstring(xml)
    items: list[dict[str, str]] = []
    for item in root.iter("item"):
        items.append(
            {
                "title": (item.findtext("title") or "").strip(),
                "link": (item.findtext("link") or "").strip(),
                "description": (item.findtext("description") or "").strip(),
                "pubDate": (item.findtext("pubDate") or "").strip(),
            }
        )
    return items


def _detect_ns(tag: str) -> str:
    """Extract the namespace from a qualified XML tag like ``{uri}urlset``."""
    if tag.startswith("{"):
        end = tag.find("}")
        return tag[1:end] if end > 1 else ""
    return ""


def _find_text(elem: ET.Element, tag: str, ns: str) -> str | None:
    found = elem.find(f"{{{ns}}}{tag}") if ns else elem.find(tag)
    if found is not None and found.text:
        return found.text.strip()
    return None


# ── Sitemap discoverer ──────────────────────────────────────────────────


class SitemapDiscoverer:
    """Discover job listings by probing common sitemap paths.

    Args:
        base_url: The careers site URL (e.g. ``https://careers.example.com``).
        ats_type: Optional ATS type hint. When set, the ``ats_type`` field
            on returned ``Job`` instances will reflect it.
        timeout: HTTP request timeout in seconds.
    """

    def __init__(
        self,
        base_url: str,
        ats_type: ATSType | None = None,
        timeout: float = 15.0,
    ) -> None:
        self.base_url = base_url.rstrip("/")
        self.ats_type = ats_type or ATSType.CUSTOM
        self.timeout = timeout

    def discover(self) -> list[Job]:
        """Run discovery and return found jobs.

        Probes known sitemap paths in order. Returns jobs from the first
        sitemap that yields results.
        """
        raw_entries = self._crawl_sitemaps()
        return [self._entry_to_job(e) for e in raw_entries]

    def _crawl_sitemaps(self) -> list[dict[str, str]]:
        for path in SITEMAP_PATHS:
            url = f"{self.base_url}{path}"
            try:
                xml = self._fetch(url)
                if xml is None:
                    continue
            except Exception:
                continue

            entries = self._try_parse(xml)
            if entries:
                return entries

            # Check if this is a sitemapindex, recurse into first sub-sitemap
            sub_sitemaps = self._try_parse_index(xml)
            if sub_sitemaps:
                for sub_url in sub_sitemaps[:5]:  # limit to 5 sub-sitemaps
                    try:
                        sub_xml = self._fetch(sub_url)
                        if sub_xml is None:
                            continue
                    except Exception:
                        continue
                    sub_entries = self._try_parse(sub_xml)
                    if sub_entries:
                        return sub_entries

        return []

    def _fetch(self, url: str) -> str | None:
        with httpx.Client(timeout=self.timeout, follow_redirects=True) as client:
            response = client.get(
                url,
                headers={
                    "User-Agent": "Mozilla/5.0 (compatible; openats-discovery/0.1)",
                    "Accept": "application/xml, application/rss+xml, text/xml, text/html",
                },
            )
            if response.status_code != 200:
                return None
            text = response.text
            if not text.strip():
                return None
            return text

    def _try_parse(self, xml: str) -> list[dict[str, str]]:
        if not xml or not xml.strip():
            return []

        # Try urlset first (most common sitemap format)
        if "<urlset" in xml[:500] or "<url " in xml[:500]:
            try:
                return _parse_urlset(xml)
            except ET.ParseError:
                pass

        # Try RSS
        if "<rss" in xml[:200] or "<channel" in xml[:500]:
            try:
                rss_items = _parse_rss(xml)
                if rss_items:
                    return [{"loc": i["link"], **i} for i in rss_items if i.get("link")]
            except ET.ParseError:
                pass

        return []

    def _try_parse_index(self, xml: str) -> list[str]:
        if "<sitemapindex" in xml[:500]:
            try:
                return _parse_sitemapindex(xml)
            except ET.ParseError:
                pass
        return []

    def _entry_to_job(self, entry: dict[str, str]) -> Job:
        loc = entry.get("loc", "").strip()
        if not loc:
            loc = entry.get("link", "").strip()
        url = loc or self.base_url

        title = entry.get("title") or _title_from_url(url)
        company = _company_name_from_url(self.base_url)
        ats_id = _ats_id_from_url(url)
        posted_at = _parse_lastmod(entry.get("lastmod")) or _parse_lastmod(entry.get("pubDate"))

        return Job(
            url=as_url(url),
            title=title,
            company=company,
            ats_type=self.ats_type,
            ats_id=ats_id,
            posted_at=posted_at,
            fetched_at=datetime.now(tz=UTC),
        )


# ── Convenience ──────────────────────────────────────────────────────────


def discover_jobs(
    url: str,
    ats_type: ATSType | None = None,
    timeout: float = 15.0,
) -> list[Job]:
    """Discover jobs from a careers URL via sitemap crawling.

    Args:
        url: The careers site URL.
        ats_type: Optional ATS type hint.
        timeout: HTTP request timeout.

    Returns:
        A list of discovered ``Job`` instances (may be empty).
    """
    return SitemapDiscoverer(url, ats_type=ats_type, timeout=timeout).discover()


# ── CLI entry point (also called from cli.py) ────────────────────────────


def discover_and_print(
    targets: list[str],
    ats_hint: str | None = None,
    db_connection: sqlite3.Connection | None = None,
) -> int:
    """Run discovery for *targets* and print results to stdout.

    Args:
        targets: List of company names, slugs, or career URLs.
        ats_hint: Optional ATS type string hint.
        db_connection: Optional DB connection for company name/slug lookup.

    Returns:
        Total number of jobs discovered.
    """
    ats_type = None
    if ats_hint:
        try:
            ats_type = ATSType(ats_hint)
        except ValueError:
            print(f"Unknown ATS type '{ats_hint}' — ignoring hint", file=sys.stderr)

    total = 0
    for target in targets:
        base_url = _resolve_target(target, db_connection)
        if base_url is None:
            print(f"  ✗ {target}: could not resolve to a URL", file=sys.stderr)
            continue

        print(f"\n  Discovering: {base_url}")
        if ats_hint:
            print(f"  ATS hint:    {ats_hint}")

        try:
            jobs = SitemapDiscoverer(base_url, ats_type=ats_type).discover()
        except Exception as exc:
            print(f"  ✗ Error: {exc}", file=sys.stderr)
            continue

        if not jobs:
            print("  → No jobs found via sitemap")
            continue

        total += len(jobs)
        print(f"  → {len(jobs)} job(s) discovered")

        if len(jobs) <= 20:
            for j in jobs:
                print(f"    • {j.title} @ {j.company} — {j.url}")
        else:
            # Show first 10 and last 5
            for j in jobs[:10]:
                print(f"    • {j.title} @ {j.company} — {j.url}")
            print(f"    … and {len(jobs) - 15} more")
            for j in jobs[-5:]:
                print(f"    • {j.title} @ {j.company} — {j.url}")

    return total


def _resolve_target(target: str, db_connection: sqlite3.Connection | None = None) -> str | None:
    """Convert a company name/slug to a careers URL, or return as-is if already a URL."""
    if target.startswith(("http://", "https://")):
        return target.rstrip("/")

    if db_connection is None:
        return None

    assert db_connection is not None
    rows = db_connection.execute(
        SELECT_COMPANY_URL_BY_SLUG_OR_NAME, (target, target),
    ).fetchall()
    if rows:
        url_val: str | None = rows[0][0]
        if url_val:
            return url_val.rstrip("/")

    return None
