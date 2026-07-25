"""Oracle Taleo Business Edition (TBE) careers collector.

Taleo Business Edition is the SMB-tier Oracle ATS — its Enterprise Edition
counterpart now lives on ``oraclecloud.com`` and is handled by ``OracleCollector``.

TBE career sites live on a sharded host pattern:

    https://{ph{c}}.tbe.taleo.net/{ph{c}NN}/ats/careers/v2/searchResults
        ?org={ORG}&cws={N}

where ``ph{c}`` (``phe``, ``phf``, ``phh``, ``phq``, etc.) is a regional shard
and ``{ph{c}NN}`` is the per-tenant instance. ``ORG`` is the company code
and ``cws`` is the career-website ID.

Job links look like:

    <h4 class="oracletaleocwsv2-head-title">
      <a href=".../viewRequisition?org=X&cws=N&rid=NNN" class="viewJobLink">
        Title
      </a>
    </h4>

The collector accepts either a full search-results URL (most reliable) or
the bare components.
"""

from __future__ import annotations

import asyncio
import html
import json
import re
from datetime import UTC, datetime
from typing import TYPE_CHECKING, Any
from urllib.parse import urlparse

import httpx

from exceptions import CollectorError
from services._base import BaseCollector, CollectorRegistry
from services._helpers import as_url, strip_html
from services._models import ATSType, EmploymentType, Job

if TYPE_CHECKING:
    pass

DETAIL_CONCURRENCY = 8

# Each job is rendered as `<a class="viewJobLink" href="...rid=NN">Title</a>`.
_JOB_LINK_RE = re.compile(
    r'<a[^>]+href="(?P<href>[^"]*viewRequisition[^"]*\brid=(?P<rid>\d+)[^"]*)"'
    r'[^>]*class="(?:[^"]*\s)?viewJobLink(?:\s[^"]*)?"[^>]*>'
    r"(?P<title>.*?)</a>",
    re.DOTALL | re.IGNORECASE,
)
_JSON_LD_RE = re.compile(
    r'<script[^>]+type=["\']application/ld\+json["\'][^>]*>([\s\S]+?)</script>',
    re.IGNORECASE,
)

_EMPLOYMENT_TYPE_PATTERNS: dict[str, EmploymentType] = {
    "intern": "INTERN",
    "internship": "INTERN",
    "trainee": "INTERN",
    "contract": "CONTRACT",
    "contractor": "CONTRACT",
    "fixed-term": "CONTRACT",
    "fixed term": "CONTRACT",
    "freelance": "CONTRACT",
    "temporary": "TEMPORARY",
    "casual": "TEMPORARY",
    "seasonal": "TEMPORARY",
    "part-time": "PART_TIME",
    "part time": "PART_TIME",
    "parttime": "PART_TIME",
    "full-time": "FULL_TIME",
    "full time": "FULL_TIME",
    "fulltime": "FULL_TIME",
    "permanent": "FULL_TIME",
}


@CollectorRegistry.register(ATSType.TALEO)
class TaleoCollector(BaseCollector):
    """Taleo TBE collector. ``company_slug`` is the full search-results URL,
    e.g. ``"https://phe.tbe.taleo.net/phe01/ats/careers/v2/searchResults?org=UH9TY5&cws=41"``.

    A bare ``ORG`` code isn't enough — the regional shard (``phe`` vs ``phh``)
    and instance number (``phe01``) and ``cws`` ID vary per tenant and there's
    no public lookup. Discover the URL once via the company's careers page.
    """

    ats = ATSType.TALEO

    def fetch(self) -> list[Job]:
        return asyncio.run(self._fetch_async())

    def get_description(self, job: Job) -> str | None:
        if job.description:
            return job.description
        copy = job.model_copy()

        async def run() -> str | None:
            async with httpx.AsyncClient(
                timeout=self.timeout,
                follow_redirects=True,
            ) as client:
                sem = asyncio.Semaphore(1)
                await self._enrich_detail(client, sem, copy)
            return copy.description

        return asyncio.run(run())

    async def _fetch_async(self) -> list[Job]:
        url = self._validate_url(self.company_slug)
        async with httpx.AsyncClient(timeout=self.timeout, follow_redirects=True) as client:
            response = await self._fetch_with_retry(
                client,
                url,
                headers={
                    "User-Agent": "Mozilla/5.0",
                    "Accept": "text/html,application/xhtml+xml",
                },
            )
            html_text = response.text
            jobs = self._parse_listing(html_text, base_url=url)
            if self.include_descriptions and jobs:
                sem = asyncio.Semaphore(DETAIL_CONCURRENCY)
                await asyncio.gather(*(self._enrich_detail(client, sem, j) for j in jobs))
        return jobs

    async def _enrich_detail(
        self,
        client: httpx.AsyncClient,
        sem: asyncio.Semaphore,
        job: Job,
    ) -> None:
        async with sem:
            try:
                response = await client.get(
                    str(job.url),
                    headers={
                        "User-Agent": "Mozilla/5.0",
                        "Accept": "text/html,application/xhtml+xml",
                    },
                )
            except httpx.HTTPError:
                return
        if response.status_code != 200:
            return
        _apply_jsonld_to_job(job, response.text)

    def _validate_url(self, slug: str) -> str:
        if not slug.startswith(("http://", "https://")):
            raise CollectorError(
                f"Taleo slug must be a full URL "
                f"(https://{{phN}}.tbe.taleo.net/{{phNN}}/ats/careers/v2/searchResults?org=X&cws=N), "
                f"got {slug!r}"
            )
        if "tbe.taleo.net" not in slug:
            raise CollectorError(f"Taleo URL must contain `tbe.taleo.net`, got {slug!r}")
        return slug.rstrip("/")

    def _parse_listing(self, html_text: str, *, base_url: str) -> list[Job]:
        company = _company_from_url(base_url)
        seen: set[str] = set()
        jobs: list[Job] = []
        for match in _JOB_LINK_RE.finditer(html_text):
            rid = match.group("rid")
            if rid in seen:
                # Each job typically renders the title link plus a redundant
                # "View" button — both have viewJobLink class. Dedup by rid.
                continue
            seen.add(rid)
            href = html.unescape(match.group("href"))
            title = strip_html(match.group("title"))
            if not title:
                continue
            jobs.append(
                Job(
                    url=as_url(href),
                    title=title,
                    company=company,
                    ats_type=ATSType.TALEO,
                    ats_id=rid,
                    location=None,  # location requires per-job page fetch
                    posted_at=None,
                    fetched_at=datetime.now(tz=UTC),
                )
            )
        return jobs


def _apply_jsonld_to_job(job: Job, html_text: str) -> None:
    """Hydrate ``job`` from the schema.org JobPosting JSON-LD on a
    Taleo TBE detail page.

    TBE pages embed a clean ``JobPosting`` block with ``description``,
    ``employmentType``, ``datePosted``, ``jobLocation`` (Place +
    PostalAddress), and ``hiringOrganization``. We pull all four when
    present.
    """
    posting = _find_job_posting(html_text)
    if posting is None:
        return

    desc = posting.get("description")
    if isinstance(desc, str) and desc.strip() and not job.description:
        job.description = strip_html(desc)[:25_000] or None

    emp = posting.get("employmentType")
    if isinstance(emp, str) and not job.employment_type:
        norm = emp.strip().lower()
        for needle, mapped in _EMPLOYMENT_TYPE_PATTERNS.items():
            if needle in norm:
                job.employment_type = mapped
                break
        if not job.commitment:
            job.commitment = emp.strip()

    if not job.posted_at:
        date_raw = posting.get("datePosted")
        if isinstance(date_raw, str) and date_raw.strip():
            cleaned = date_raw.strip().replace("Z", "+00:00")
            try:
                job.posted_at = datetime.fromisoformat(cleaned)
            except ValueError:
                # TBE often ships ``"2025-07-28 00:00:00.0"`` form.
                cleaned_no_tz = re.sub(r"\.\d+$", "", cleaned)
                for fmt in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%d"):
                    try:
                        job.posted_at = datetime.strptime(cleaned_no_tz, fmt)
                        break
                    except ValueError:
                        continue

    if not job.location:
        loc = _location_from_jsonld(posting.get("jobLocation"))
        if loc:
            job.location = loc

    org = posting.get("hiringOrganization")
    if isinstance(org, dict):
        name = org.get("name")
        if isinstance(name, str) and name.strip():
            job.company = name.strip()


def _find_job_posting(html_text: str) -> dict[str, Any] | None:
    for match in _JSON_LD_RE.finditer(html_text):
        body = match.group(1).strip()
        try:
            data = json.loads(body)
        except json.JSONDecodeError:
            continue
        if isinstance(data, dict) and data.get("@type") == "JobPosting":
            return data
        if isinstance(data, list):
            for item in data:
                if isinstance(item, dict) and item.get("@type") == "JobPosting":
                    return item
    return None


def _location_from_jsonld(value: object) -> str | None:
    candidates = value if isinstance(value, list) else [value]
    for c in candidates:
        if not isinstance(c, dict):
            continue
        addr = c.get("address")
        if not isinstance(addr, dict):
            continue
        parts = [
            str(addr.get(k) or "").strip()
            for k in ("addressLocality", "addressRegion", "addressCountry")
            if addr.get(k)
        ]
        joined = ", ".join(p for p in parts if p)
        if joined:
            return joined
    return None


def _company_from_url(url: str) -> str:
    """Extract the ``org`` query parameter as the company name. Falls back
    to the host's first label."""
    m = re.search(r"[?&]org=([^&#]+)", url)
    if m:
        return m.group(1)
    host = urlparse(url).hostname or ""
    return host.split(".", 1)[0]
