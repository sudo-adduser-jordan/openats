"""Web search-based company discovery.

Uses search engine queries to discover company slugs for multi-tenant ATS
platforms. Queries like ``site:apply.workable.com`` return URLs from which
company slugs can be extracted.
"""

from __future__ import annotations

import re
from typing import ClassVar

import httpx

from services._models import ATSType, Company
from services.discover._base import BaseDiscovery, DiscoveryError, DiscoveryRegistry


class SearchDiscovery(BaseDiscovery):
    """Generic web search-based discovery for multi-tenant ATS platforms.

    Subclasses set ``SEARCH_DOMAIN``, ``URL_PATTERN``, and ``ATS_TYPE``
    to configure per-ATS search behavior.
    """

    SEARCH_DOMAIN: ClassVar[str]  # e.g. "apply.workable.com"
    URL_PATTERN: ClassVar[re.Pattern[str]]  # e.g. r"https://([^.]+)\.apply\.workable\.com"
    ATS_TYPE: ClassVar[ATSType]
    SEARCH_URL: ClassVar[str] = "https://www.google.com/search"
    RESULTS_PER_PAGE: ClassVar[int] = 100

    def __init__(self, *, timeout: float = 30.0, max_pages: int = 10) -> None:
        super().__init__(timeout=timeout)
        self.max_pages = max_pages

    async def discover(self) -> list[Company]:
        """Discover companies via web search."""
        companies: list[Company] = []
        seen_slugs: set[str] = set()

        async with httpx.AsyncClient(
            timeout=self.timeout,
            follow_redirects=True,
        ) as client:
            for page in range(self.max_pages):
                try:
                    urls = await self._search_page(client, page)
                except DiscoveryError:
                    break

                for url in urls:
                    match = self.URL_PATTERN.search(url)
                    if match:
                        slug = match.group(1)
                        if slug not in seen_slugs:
                            seen_slugs.add(slug)
                            companies.append(
                                Company(
                                    slug=slug,
                                    name=slug,
                                    ats=self.ATS_TYPE,
                                )
                            )

                if len(urls) < self.RESULTS_PER_PAGE:
                    break

        return companies

    async def _search_page(
        self,
        client: httpx.AsyncClient,
        page: int,
    ) -> list[str]:
        """Execute a search query and return discovered URLs."""
        params = {
            "q": f"site:{self.SEARCH_DOMAIN}",
            "start": str(page * self.RESULTS_PER_PAGE),
            "num": str(self.RESULTS_PER_PAGE),
        }
        response = await self._fetch_with_retry(
            client,
            self.SEARCH_URL,
            params=params,
        )
        # Extract URLs from search results
        urls = re.findall(r'https?://[^\s"<>]+', response.text)
        return [u for u in urls if self.SEARCH_DOMAIN in u]


@DiscoveryRegistry.register(ATSType.GREENHOUSE)
class GreenhouseSearchDiscovery(SearchDiscovery):
    """Discover Greenhouse companies via web search."""

    SEARCH_DOMAIN = "boards-api.greenhouse.io"
    URL_PATTERN = re.compile(r"https://boards-api\.greenhouse\.io/v1/boards/([^/]+)/")
    ATS_TYPE = ATSType.GREENHOUSE


@DiscoveryRegistry.register(ATSType.LEVER)
class LeverSearchDiscovery(SearchDiscovery):
    """Discover Lever companies via web search."""

    SEARCH_DOMAIN = "jobs.lever.co"
    URL_PATTERN = re.compile(r"https://jobs\.lever\.co/([^/]+)")
    ATS_TYPE = ATSType.LEVER


@DiscoveryRegistry.register(ATSType.WORKABLE)
class WorkableSearchDiscovery(SearchDiscovery):
    """Discover Workable companies via web search."""

    SEARCH_DOMAIN = "apply.workable.com"
    URL_PATTERN = re.compile(r"https://([^.]+)\.apply\.workable\.com")
    ATS_TYPE = ATSType.WORKABLE


@DiscoveryRegistry.register(ATSType.ASHBY)
class AshbySearchDiscovery(SearchDiscovery):
    """Discover Ashby companies via web search."""

    SEARCH_DOMAIN = "jobs.ashbyhq.com"
    URL_PATTERN = re.compile(r"https://jobs\.ashbyhq\.com/([^/]+)")
    ATS_TYPE = ATSType.ASHBY


@DiscoveryRegistry.register(ATSType.SMARTRECRUITERS)
class SmartRecruitersSearchDiscovery(SearchDiscovery):
    """Discover SmartRecruiters companies via web search."""

    SEARCH_DOMAIN = "jobs.smartrecruiters.com"
    URL_PATTERN = re.compile(r"https://jobs\.smartrecruiters\.com/([^/]+)")
    ATS_TYPE = ATSType.SMARTRECRUITERS


@DiscoveryRegistry.register(ATSType.RECRUITEE)
class RecruiteeSearchDiscovery(SearchDiscovery):
    """Discover Recruitee companies via web search."""

    SEARCH_DOMAIN = "recruitee.com"
    URL_PATTERN = re.compile(r"https://([^.]+)\.recruitee\.com")
    ATS_TYPE = ATSType.RECRUITEE


@DiscoveryRegistry.register(ATSType.BAMBOOHR)
class BambooHRSearchDiscovery(SearchDiscovery):
    """Discover BambooHR companies via web search."""

    SEARCH_DOMAIN = "bamboohr.com"
    URL_PATTERN = re.compile(r"https://([^.]+)\.bamboohr\.com")
    ATS_TYPE = ATSType.BAMBOOHR


@DiscoveryRegistry.register(ATSType.PINPOINT)
class PinpointSearchDiscovery(SearchDiscovery):
    """Discover Pinpoint companies via web search."""

    SEARCH_DOMAIN = "pinpointhq.com"
    URL_PATTERN = re.compile(r"https://([^.]+)\.pinpointhq\.com")
    ATS_TYPE = ATSType.PINPOINT


@DiscoveryRegistry.register(ATSType.BREEZY)
class BreezySearchDiscovery(SearchDiscovery):
    """Discover Breezy companies via web search."""

    SEARCH_DOMAIN = "breezy.hr"
    URL_PATTERN = re.compile(r"https://([^.]+)\.breezy\.hr")
    ATS_TYPE = ATSType.BREEZY


@DiscoveryRegistry.register(ATSType.PERSONIO)
class PersonioSearchDiscovery(SearchDiscovery):
    """Discover Personio companies via web search."""

    SEARCH_DOMAIN = "jobs.personio.com"
    URL_PATTERN = re.compile(r"https://([^.]+)\.jobs\.personio\.com")
    ATS_TYPE = ATSType.PERSONIO


@DiscoveryRegistry.register(ATSType.RIPPLING)
class RipplingSearchDiscovery(SearchDiscovery):
    """Discover Rippling companies via web search."""

    SEARCH_DOMAIN = "rippling.com"
    URL_PATTERN = re.compile(r"https://([^.]+)\.rippling\.com")
    ATS_TYPE = ATSType.RIPPLING
