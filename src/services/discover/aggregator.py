"""Job aggregator-based company discovery.

Discovers companies by querying job aggregator sites that index multiple
ATS platforms. These aggregators expose public APIs or pages that list
companies and their ATS types.
"""

from __future__ import annotations

from typing import ClassVar

import httpx

from services._models import ATSType, Company
from services.discover._base import BaseDiscovery, DiscoveryError


class AggregatorDiscovery(BaseDiscovery):
    """Base class for aggregator-based discovery.

    Subclasses implement ``discover()`` to fetch from a specific aggregator.
    """

    pass


class TheirStackDiscovery(AggregatorDiscovery):
    """Discover companies via TheirStack.com.

    TheirStack indexes jobs from 351k+ sources including Greenhouse, Lever,
    Workday, SmartRecruiters, and others. Their public search API exposes
    company-ATS mappings without authentication.
    """

    BASE_URL: ClassVar[str] = "https://www.theirstack.com/api"
    ATS_MAP: ClassVar[dict[str, ATSType]] = {
        "greenhouse": ATSType.GREENHOUSE,
        "lever": ATSType.LEVER,
        "workday": ATSType.WORKDAY,
        "smartrecruiters": ATSType.SMARTRECRUITERS,
        "ashby": ATSType.ASHBY,
        "workable": ATSType.WORKABLE,
        "bamboohr": ATSType.BAMBOOHR,
        "recruitee": ATSType.RECRUITEE,
        "jazzhr": ATSType.JAZZHR,
        "breezy": ATSType.BREEZY,
        "pinpoint": ATSType.PINPOINT,
        "personio": ATSType.PERSONIO,
        "rippling": ATSType.RIPPLING,
    }

    def __init__(self, *, timeout: float = 30.0, max_pages: int = 10) -> None:
        super().__init__(timeout=timeout)
        self.max_pages = max_pages

    async def discover(self) -> list[Company]:
        """Discover companies via TheirStack search API."""
        companies: list[Company] = []
        seen: set[tuple[str, str]] = set()

        async with httpx.AsyncClient(timeout=self.timeout) as client:
            for page in range(self.max_pages):
                try:
                    page_companies = await self._fetch_page(client, page)
                except DiscoveryError:
                    break

                for company in page_companies:
                    key = (company.ats.value, company.slug)
                    if key not in seen:
                        seen.add(key)
                        companies.append(company)

                if len(page_companies) == 0:
                    break

        return companies

    async def _fetch_page(
        self,
        client: httpx.AsyncClient,
        page: int,
    ) -> list[Company]:
        """Fetch a page of results from TheirStack."""
        # TheirStack uses a POST endpoint for search
        url = f"{self.BASE_URL}/v1/jobs/search"
        body = {
            "page": page,
            "per_page": 100,
        }
        try:
            response = await client.post(url, json=body)
        except httpx.HTTPError as exc:
            raise DiscoveryError(f"TheirStack request failed: {exc}") from exc

        if response.status_code != 200:
            raise DiscoveryError(f"TheirStack returned {response.status_code}")

        data = response.json()
        companies: list[Company] = []

        # Parse results — exact structure depends on TheirStack API version
        for job in data.get("jobs", []):
            ats_type_str = job.get("ats_type", "").lower()
            company_name = job.get("company_name", "")
            company_slug = job.get("company_slug", "")

            if ats_type_str in self.ATS_MAP and company_slug:
                companies.append(
                    Company(
                        slug=company_slug,
                        name=company_name or company_slug,
                        ats=self.ATS_MAP[ats_type_str],
                    )
                )

        return companies


class JobsPipeDiscovery(AggregatorDiscovery):
    """Discover companies via JobsPipe.

    JobsPipe indexes every public Greenhouse board and provides a
    searchable API.
    """

    BASE_URL: ClassVar[str] = "https://jobspipe.com/api"

    def __init__(self, *, timeout: float = 30.0, max_pages: int = 10) -> None:
        super().__init__(timeout=timeout)
        self.max_pages = max_pages

    async def discover(self) -> list[Company]:
        """Discover Greenhouse companies via JobsPipe."""
        companies: list[Company] = []
        seen: set[str] = set()

        async with httpx.AsyncClient(timeout=self.timeout) as client:
            for page in range(self.max_pages):
                try:
                    page_companies = await self._fetch_page(client, page)
                except DiscoveryError:
                    break

                for company in page_companies:
                    if company.slug not in seen:
                        seen.add(company.slug)
                        companies.append(company)

                if len(page_companies) == 0:
                    break

        return companies

    async def _fetch_page(
        self,
        client: httpx.AsyncClient,
        page: int,
    ) -> list[Company]:
        """Fetch a page of Greenhouse boards from JobsPipe."""
        url = f"{self.BASE_URL}/v1/boards"
        params = {"page": page, "per_page": 100}

        try:
            response = await client.get(url, params=params)
        except httpx.HTTPError as exc:
            raise DiscoveryError(f"JobsPipe request failed: {exc}") from exc

        if response.status_code != 200:
            raise DiscoveryError(f"JobsPipe returned {response.status_code}")

        data = response.json()
        companies: list[Company] = []

        for board in data.get("boards", []):
            slug = board.get("slug", "")
            name = board.get("name", slug)
            if slug:
                companies.append(
                    Company(
                        slug=slug,
                        name=name,
                        ats=ATSType.GREENHOUSE,
                    )
                )

        return companies
