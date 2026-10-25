"""JazzHR sitemap feed-based company discovery.

JazzHR publishes Google Merchant-style XML feeds at:
    https://app.jazz.co/feeds/google/xml/{0-4}

These 5 shards contain thousands of job URLs from which company slugs
can be extracted. This is the highest-value discovery source — 5 HTTP
requests yield thousands of unique JazzHR company slugs. It is also, as
of the source survey in ``_sources.py``, the only ATS that publishes an
unauthenticated directory of its own tenants.

URL pattern in feeds:
    https://{slug}.applytojob.com/apply/{id}/...
"""

from __future__ import annotations

import re
from typing import ClassVar

from services._models import ATSType
from services.discover._base import DiscoveryRegistry
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

    ats = ATSType.JAZZHR
    SOURCE_URL = JAZZHR_FEED_URLS[0]
    FEED_URLS: ClassVar[list[str]] = JAZZHR_FEED_URLS
    URL_PATTERN: ClassVar[re.Pattern[str]] = JAZZHR_URL_PATTERN
