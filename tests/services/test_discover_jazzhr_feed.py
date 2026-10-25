"""Discovery-side tests for JazzHR.

``tests/services/test_jazzhr.py`` covers the *collector* (parsing a tenant's
``/apply/jobs`` page). This file covers the *discoverer*: reading the five
public feed shards and turning job URLs into tenant slugs.

JazzHR is the only ATS openats supports that publishes an unauthenticated
directory of its own tenants, which is why it is the one live source in the
survey — see ``services.discover._sources``.
"""

from __future__ import annotations

from services._models import ATSType, Company
from services.discover.jazzhr import (
    JAZZHR_FEED_URLS,
    JAZZHR_URL_PATTERN,
    JazzHRSitemapDiscovery,
)


def _feed(*slugs: str) -> str:
    """Build a shard in the shape app.jazz.co emits."""
    items = "\n".join(
        f"    <item><link>https://{slug}.applytojob.com/apply/{i}/Some-Role</link></item>"
        for i, slug in enumerate(slugs)
    )
    return (
        '<?xml version="1.0" encoding="UTF-8"?>\n'
        '<rss version="2.0"><channel>\n'
        "  <title>JazzHR</title>\n"
        "  <link>https://app.jazz.co/</link>\n"
        f"{items}\n"
        "</channel></rss>"
    )


def test_discoverer_contract() -> None:
    discoverer = JazzHRSitemapDiscovery()
    assert discoverer.ats is ATSType.JAZZHR
    assert discoverer.FEED_URLS == JAZZHR_FEED_URLS
    assert len(discoverer.FEED_URLS) == 5
    assert discoverer.SOURCE_URL == JAZZHR_FEED_URLS[0]
    assert discoverer.FEED_URLS[4].endswith("/4")


def test_url_pattern_extracts_tenant_slug_only() -> None:
    match = JAZZHR_URL_PATTERN.search("https://acme-west_2.applytojob.com/apply/12/Role")
    assert match is not None
    assert match.group(1) == "acme-west_2"

    # Paths that are not tenant job pages do not match at all.
    assert JAZZHR_URL_PATTERN.search("https://app.jazz.co/feeds/google/xml/0") is None


def test_extracts_slugs_and_dedupes_within_a_shard() -> None:
    discoverer = JazzHRSitemapDiscovery()
    companies = discoverer._extract_companies(_feed("acme", "acme", "beta"))

    assert [company.slug for company in companies] == ["acme", "beta"]
    assert all(company.ats is ATSType.JAZZHR for company in companies)


async def test_discover_reads_every_shard_and_survives_a_failing_one(httpx_mock) -> None:
    httpx_mock.add_response(url=JAZZHR_FEED_URLS[0], text=_feed("acme", "beta"))
    httpx_mock.add_response(url=JAZZHR_FEED_URLS[1], status_code=404)
    httpx_mock.add_response(url=JAZZHR_FEED_URLS[2], text=_feed("beta", "gamma"))
    httpx_mock.add_response(url=JAZZHR_FEED_URLS[3], text=_feed("delta"))
    httpx_mock.add_response(url=JAZZHR_FEED_URLS[4], text=_feed("epsilon"))

    companies = await JazzHRSitemapDiscovery().discover()

    # Shard 1 404s; the other four contribute and slugs are unique across them.
    assert [company.slug for company in companies] == [
        "acme",
        "beta",
        "gamma",
        "delta",
        "epsilon",
    ]
    assert len(httpx_mock.get_requests()) == 5


async def test_discover_returns_nothing_when_every_shard_fails(httpx_mock) -> None:
    for feed_url in JAZZHR_FEED_URLS:
        httpx_mock.add_response(url=feed_url, status_code=404)

    companies = await JazzHRSitemapDiscovery().discover()

    assert companies == []


def test_companies_are_plain_slugs_ready_for_the_database() -> None:
    company = JazzHRSitemapDiscovery()._extract_companies(_feed("acme"))[0]
    assert isinstance(company, Company)
    assert company.careers_url is None
    assert company.website is None
