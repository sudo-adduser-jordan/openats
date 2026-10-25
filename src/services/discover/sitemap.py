"""Sitemap and RSS/Atom feed-based company discovery.

Parses XML sitemaps and RSS/Atom feeds to discover company slugs from URL
patterns. Used as a base class for ATS-specific sitemap discoverers.

Three shapes are understood:

* ``<urlset><url><loc>`` — a plain sitemap.
* ``<rss><channel><item><link>|<guid>`` — RSS.
* ``<feed><entry><link href=`` — Atom, whose ``link`` carries an attribute
  rather than text.

A ``<sitemapindex>`` is followed one level deep: its ``<loc>`` entries point at
further sitemaps, not at jobs, so feeding them to ``URL_PATTERN`` (what the
naive "match every ``<loc>``" approach does) silently discards them.
"""

from __future__ import annotations

import logging
import re
import xml.etree.ElementTree as ET
from collections.abc import Iterator
from typing import ClassVar

import httpx

from services._models import ATSType, Company
from services.discover._base import BaseDiscovery, DiscoveryError

log = logging.getLogger(__name__)

#: Levels of ``<sitemapindex>`` nesting we will follow. A well-behaved feed
#: generator is one index deep; anything deeper is a runaway or a trap.
MAX_SITEMAP_DEPTH: int = 1

#: XML element names that carry a URL, matched on the local (namespace-free)
#: part of the tag so both default-namespaced sitemaps and Atom feeds work.
_URL_CONTAINERS: frozenset[str] = frozenset({"url", "item", "entry"})
_URL_FIELDS: frozenset[str] = frozenset({"loc", "link", "guid"})


class SitemapDiscovery(BaseDiscovery):
    """Base class for sitemap/RSS/Atom feed-based discovery.

    Subclasses set ``ats``, ``FEED_URLS``, and ``URL_PATTERN`` to configure
    per-ATS sitemap behavior.
    """

    ats: ClassVar[ATSType]
    FEED_URLS: ClassVar[list[str]]  # List of sitemap/feed URLs to fetch
    URL_PATTERN: ClassVar[re.Pattern[str]]  # Pattern to extract slugs from URLs

    async def discover(self) -> list[Company]:
        """Fetch and parse every configured feed, deduplicating across them."""
        companies: list[Company] = []
        seen_slugs: set[str] = set()

        async with httpx.AsyncClient(timeout=self.timeout) as client:
            # dict.fromkeys() de-dupes the URL list while keeping source order.
            for feed_url in dict.fromkeys(self.FEED_URLS):
                try:
                    feed_companies = await self._parse_feed(client, feed_url)
                except DiscoveryError as exc:
                    log.warning(
                        "discover_feed_failed ats=%s url=%s error=%s",
                        self.ats.value,
                        feed_url,
                        exc,
                    )
                    continue

                for company in feed_companies:
                    if company.slug not in seen_slugs:
                        seen_slugs.add(company.slug)
                        companies.append(company)

        return companies

    async def _parse_feed(
        self,
        client: httpx.AsyncClient,
        feed_url: str,
        *,
        depth: int = 0,
    ) -> list[Company]:
        """Fetch and parse a single feed URL, following sitemap indexes."""
        response = await self._fetch_with_retry(client, feed_url)
        root = self._parse_xml(response.text, feed_url)
        if root is None:
            return []

        if self._local_name(root.tag) == "sitemapindex":
            if depth >= MAX_SITEMAP_DEPTH:
                log.warning("discover_sitemap_too_deep ats=%s url=%s", self.ats.value, feed_url)
                return []
            companies: list[Company] = []
            seen: set[str] = set()
            for child_url in self._child_urls(root):
                try:
                    nested = await self._parse_feed(client, child_url, depth=depth + 1)
                except DiscoveryError as exc:
                    log.warning(
                        "discover_feed_failed ats=%s url=%s error=%s",
                        self.ats.value,
                        child_url,
                        exc,
                    )
                    continue
                for company in nested:
                    if company.slug not in seen:
                        seen.add(company.slug)
                        companies.append(company)
            return companies

        return self._extract_from_root(root)

    def _extract_companies(self, xml_text: str) -> list[Company]:
        """Extract company slugs from XML content. ``[]`` when unparseable."""
        root = self._parse_xml(xml_text, None)
        if root is None:
            return []
        return self._extract_from_root(root)

    def _extract_from_root(self, root: ET.Element) -> list[Company]:
        companies: list[Company] = []
        seen: set[str] = set()
        for url in self._urls_from(root):
            match = self.URL_PATTERN.search(url)
            if match is None:
                continue
            slug = match.group(1)
            if slug in seen:
                continue
            seen.add(slug)
            companies.append(Company(slug=slug, name=slug, ats=self.ats))
        return companies

    def _parse_xml(self, xml_text: str, feed_url: str | None) -> ET.Element | None:
        try:
            return ET.fromstring(xml_text)
        except ET.ParseError as exc:
            log.warning(
                "discover_feed_parse_error ats=%s url=%s error=%s",
                self.ats.value,
                feed_url or "<inline>",
                exc,
            )
            return None

    def _urls_from(self, root: ET.Element) -> Iterator[str]:
        """Yield every candidate URL held by a parsed feed."""
        root_name = self._local_name(root.tag)
        if root_name == "urlset":
            for container in self._named(root, "url"):
                yield from self._field_texts(container)
        elif root_name in ("rss", "feed"):
            for container in root.iter():
                if not isinstance(container.tag, str):
                    continue
                if self._local_name(container.tag) not in _URL_CONTAINERS:
                    continue
                yield from self._field_texts(container)
        # A <sitemapindex> has no job URLs of its own; its <loc> entries are
        # followed by _parse_feed() instead.

    @classmethod
    def _field_texts(cls, container: ET.Element) -> Iterator[str]:
        for child in container:
            if not isinstance(child.tag, str):
                continue
            if cls._local_name(child.tag) not in _URL_FIELDS:
                continue
            text = (child.text or "").strip()
            if text:
                yield text
            # Atom <link href="..."/> carries the URL as an attribute.
            href = (child.get("href") or "").strip()
            if href:
                yield href

    @classmethod
    def _child_urls(cls, root: ET.Element) -> Iterator[str]:
        for elem in root.iter():
            if isinstance(elem.tag, str) and cls._local_name(elem.tag) == "loc":
                text = (elem.text or "").strip()
                if text:
                    yield text

    @staticmethod
    def _named(root: ET.Element, local_name: str) -> Iterator[ET.Element]:
        for elem in root.iter():
            if isinstance(elem.tag, str) and elem.tag.rsplit("}", 1)[-1] == local_name:
                yield elem

    @staticmethod
    def _local_name(tag: str) -> str:
        return tag.rsplit("}", 1)[-1]
