"""XML feed parsing for ``SitemapDiscovery``.

The base class is the only extension point left in the discover package, so
its parsing rules are worth pinning precisely: which containers are read,
how namespaces are handled, and what happens to a ``<sitemapindex>`` — which
the original implementation silently threw away by feeding index URLs to
``URL_PATTERN``.
"""

from __future__ import annotations

import re

import httpx

from services._models import ATSType, Company
from services.discover.sitemap import MAX_SITEMAP_DEPTH, SitemapDiscovery

URL_PATTERN = re.compile(r"https://([a-z0-9_-]+)\.example-jobs\.com/")

SITEMAP_NS = "http://www.sitemaps.org/schemas/sitemap/0.9"
ATOM_NS = "http://www.w3.org/2005/Atom"


def make_discoverer(feed_urls: list[str]) -> SitemapDiscovery:
    """A concrete discoverer for a synthetic ``example-jobs.com`` ATS."""
    return type(
        "_TestFeedDiscovery",
        (SitemapDiscovery,),
        {"ats": ATSType.GREENHOUSE, "FEED_URLS": feed_urls, "URL_PATTERN": URL_PATTERN},
    )()


def slugs(companies: list[Company]) -> list[str]:
    return [company.slug for company in companies]


URLSET = f"""<?xml version="1.0" encoding="UTF-8"?>
<urlset xmlns="{SITEMAP_NS}">
  <url><loc>https://acme.example-jobs.com/apply/1</loc></url>
  <url><loc>https://acme.example-jobs.com/apply/2</loc></url>
  <url><loc>https://beta.example-jobs.com/apply/3</loc></url>
</urlset>
"""

RSS = """<?xml version="1.0" encoding="UTF-8"?>
<rss version="2.0">
  <channel>
    <title>Example Jobs</title>
    <link>https://blog.example-jobs.com/</link>
    <item><link>https://acme.example-jobs.com/apply/1</link></item>
    <item><guid isPermaLink="false">https://beta.example-jobs.com/apply/2</guid></item>
  </channel>
</rss>
"""

ATOM = f"""<?xml version="1.0" encoding="UTF-8"?>
<feed xmlns="{ATOM_NS}">
  <title>Example Jobs</title>
  <link href="https://blog.example-jobs.com/"/>
  <entry><link href="https://acme.example-jobs.com/apply/1"/></entry>
  <entry><link href="https://beta.example-jobs.com/apply/2"/></entry>
</feed>
"""


def test_namespaced_urlset_extracts_and_dedupes_slugs() -> None:
    companies = make_discoverer([])._extract_companies(URLSET)
    assert slugs(companies) == ["acme", "beta"]
    assert all(company.ats is ATSType.GREENHOUSE for company in companies)
    assert all(company.name == company.slug for company in companies)


def test_unnamespaced_urlset_is_supported() -> None:
    xml = "<urlset><url><loc>https://acme.example-jobs.com/apply/1</loc></url></urlset>"
    assert slugs(make_discoverer([])._extract_companies(xml)) == ["acme"]


def test_rss_reads_items_only_not_the_channel_link() -> None:
    """The channel's own ``<link>`` matches the pattern but is not a tenant."""
    assert slugs(make_discoverer([])._extract_companies(RSS)) == ["acme", "beta"]


def test_atom_link_carries_href_not_text() -> None:
    assert slugs(make_discoverer([])._extract_companies(ATOM)) == ["acme", "beta"]


def test_malformed_xml_returns_empty_list() -> None:
    assert make_discoverer([])._extract_companies("<urlset><url>") == []


def test_non_feed_payload_returns_empty_list() -> None:
    assert make_discoverer([])._extract_companies("<html><body>Blocked</body></html>") == []


def test_sitemap_index_yields_no_companies_on_its_own() -> None:
    index = f"""<sitemapindex xmlns="{SITEMAP_NS}">
      <sitemap><loc>https://example.test/sitemap-0.xml</loc></sitemap>
      <sitemap><loc>https://example.test/sitemap-1.xml</loc></sitemap>
    </sitemapindex>"""
    assert make_discoverer([])._extract_companies(index) == []


async def test_parse_feed_follows_a_sitemap_index(httpx_mock) -> None:
    index = f"""<sitemapindex xmlns="{SITEMAP_NS}">
      <sitemap><loc>https://example.test/sitemap-0.xml</loc></sitemap>
      <sitemap><loc>https://example.test/sitemap-1.xml</loc></sitemap>
    </sitemapindex>"""
    httpx_mock.add_response(url="https://example.test/index.xml", text=index)
    httpx_mock.add_response(
        url="https://example.test/sitemap-0.xml",
        text=URLSET,
    )
    httpx_mock.add_response(
        url="https://example.test/sitemap-1.xml",
        text="""<urlset><url><loc>https://gamma.example-jobs.com/apply/9</loc></url></urlset>""",
    )

    discoverer = make_discoverer([])
    async with httpx.AsyncClient() as client:
        companies = await discoverer._parse_feed(client, "https://example.test/index.xml")

    assert slugs(companies) == ["acme", "beta", "gamma"]
    assert len(httpx_mock.get_requests()) == 3


async def test_sitemap_index_nesting_stops_at_the_depth_limit(httpx_mock) -> None:
    """An index pointing at another index is not followed past the limit."""
    assert MAX_SITEMAP_DEPTH == 1
    outer = f"""<sitemapindex xmlns="{SITEMAP_NS}">
      <sitemap><loc>https://example.test/inner.xml</loc></sitemap>
    </sitemapindex>"""
    inner = f"""<sitemapindex xmlns="{SITEMAP_NS}">
      <sitemap><loc>https://example.test/deepest.xml</loc></sitemap>
    </sitemapindex>"""
    httpx_mock.add_response(url="https://example.test/outer.xml", text=outer)
    httpx_mock.add_response(url="https://example.test/inner.xml", text=inner)

    discoverer = make_discoverer([])
    async with httpx.AsyncClient() as client:
        companies = await discoverer._parse_feed(client, "https://example.test/outer.xml")

    assert companies == []
    # The deepest sitemap is never requested.
    assert len(httpx_mock.get_requests()) == 2


async def test_discover_skips_a_failing_feed_and_keeps_the_rest(httpx_mock) -> None:
    feeds = [
        "https://example.test/a.xml",
        "https://example.test/b.xml",
        "https://example.test/c.xml",
    ]
    httpx_mock.add_response(url=feeds[0], text=URLSET)
    httpx_mock.add_response(url=feeds[1], status_code=404)
    httpx_mock.add_response(
        url=feeds[2],
        text="<urlset><url><loc>https://gamma.example-jobs.com/apply/9</loc></url></urlset>",
    )

    companies = await make_discoverer(feeds).discover()

    # Feed b 404s; a and c still contribute, and slugs are deduped across feeds.
    assert slugs(companies) == ["acme", "beta", "gamma"]
    assert len(httpx_mock.get_requests()) == 3


async def test_discover_dedupes_across_feeds(httpx_mock) -> None:
    feeds = ["https://example.test/a.xml", "https://example.test/b.xml"]
    httpx_mock.add_response(url=feeds[0], text=URLSET)
    httpx_mock.add_response(url=feeds[1], text=URLSET)

    companies = await make_discoverer(feeds).discover()

    assert slugs(companies) == ["acme", "beta"]


async def test_discover_dedupes_repeated_feed_urls(httpx_mock) -> None:
    """The same URL listed twice is fetched once."""
    feeds = ["https://example.test/a.xml", "https://example.test/a.xml"]
    httpx_mock.add_response(url=feeds[0], text=URLSET)

    companies = await make_discoverer(feeds).discover()

    assert slugs(companies) == ["acme", "beta"]
    assert len(httpx_mock.get_requests()) == 1
