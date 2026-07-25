"""JazzHR sitemap feed-based company discovery.

JazzHR publishes Google Merchant-style XML feeds at:
    https://app.jazz.co/feeds/google/xml/{0-4}

These 5 shards contain thousands of job URLs from which company slugs
can be extracted. This is the highest-value discovery source — 5 HTTP
requests yield thousands of unique JazzHR company slugs.

URL pattern in feeds:
    https://{slug}.applytojob.com/apply/{id}/...
"""

from __future__ import annotations

import re

import httpx

from services._models import ATSType, Company
from services.discover._base import DiscoveryError, DiscoveryRegistry
from services.discover.sitemap import SitemapDiscovery

# JazzHR feed shards
JAZZHR_FEED_URLS = [f"https://app.jazz.co/feeds/google/xml/{i}" for i in range(5)]

# Pattern to extract company slug from JazzHR job URLs
# Matches: https://{slug}.applytojob.com/apply/{id}/...
JAZZHR_URL_PATTERN = re.compile(r"https?://([a-zA-Z0-9_-]+)\.applytojob\.com/apply/")


@DiscoveryRegistry.register(ATSType.JAZZHR)
class JazzHRSitemapDiscovery(SitemapDiscovery):
    """JazzHR sitemap feed discovery.

    Fetches 5 XML feed shards from app.jazz.co and extracts company slugs
    from job URLs. Each shard contains hundreds of job listings from
    different JazzHR tenants.
    """

    ATS_TYPE = ATSType.JAZZHR
    FEED_URLS = JAZZHR_FEED_URLS
    URL_PATTERN = JAZZHR_URL_PATTERN

    async def discover(self) -> list[Company]:
        """Discover JazzHR companies from feed shards."""
        companies: list[Company] = []
        seen_slugs: set[str] = set()

        async with httpx.AsyncClient(timeout=self.timeout) as client:
            for feed_url in self.FEED_URLS:
                try:
                    response = await self._fetch_with_retry(client, feed_url)
                    feed_companies = self._extract_companies(response.text)
                    for company in feed_companies:
                        if company.slug not in seen_slugs:
                            seen_slugs.add(company.slug)
                            companies.append(company)
                except DiscoveryError as exc:
                    # Log but continue with other shards
                    import logging

                    log = logging.getLogger(__name__)
                    log.warning(
                        "JazzHR feed failed: %s — %s",
                        feed_url,
                        exc,
                    )
                    continue

        return companies
