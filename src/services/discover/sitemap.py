"""Sitemap and RSS feed-based company discovery.

Parses XML sitemaps and RSS feeds to discover company slugs from URL patterns.
Used as a base class for ATS-specific sitemap discoverers.
"""

from __future__ import annotations

import re
import xml.etree.ElementTree as ET
from typing import ClassVar

import httpx

from services._models import ATSType, Company
from services.discover._base import BaseDiscovery, DiscoveryError


class SitemapDiscovery(BaseDiscovery):
    """Base class for sitemap/RSS feed-based discovery.

    Subclasses set ``ATS_TYPE``, ``FEED_URLS``, and ``URL_PATTERN``
    to configure per-ATS sitemap behavior.
    """

    ATS_TYPE: ClassVar[ATSType]
    FEED_URLS: ClassVar[list[str]]  # List of sitemap/feed URLs to fetch
    URL_PATTERN: ClassVar[re.Pattern[str]]  # Pattern to extract slugs from URLs

    async def discover(self) -> list[Company]:
        """Fetch and parse all configured feeds."""
        companies: list[Company] = []
        seen_slugs: set[str] = set()

        async with httpx.AsyncClient(timeout=self.timeout) as client:
            for feed_url in self.FEED_URLS:
                try:
                    feed_companies = await self._parse_feed(client, feed_url)
                except DiscoveryError:
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
    ) -> list[Company]:
        """Fetch and parse a single feed URL."""
        response = await self._fetch_with_retry(client, feed_url)
        return self._extract_companies(response.text)

    def _extract_companies(self, xml_text: str) -> list[Company]:
        """Extract company slugs from XML content."""
        companies: list[Company] = []
        try:
            root = ET.fromstring(xml_text)
        except ET.ParseError:
            return companies

        # Handle both sitemap and RSS formats
        # Sitemap: <urlset><url><loc>...
        # RSS: <rss><channel><item><link>... or <guid>...
        for elem in root.iter():
            if elem.tag in ("loc", "link", "guid"):
                text = (elem.text or "").strip()
                if text:
                    match = self.URL_PATTERN.search(text)
                    if match:
                        slug = match.group(1)
                        companies.append(
                            Company(
                                slug=slug,
                                name=slug,
                                ats=self.ATS_TYPE,
                            )
                        )

        return companies
