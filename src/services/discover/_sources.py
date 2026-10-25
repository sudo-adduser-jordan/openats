"""The company-discovery source survey: what was probed, and what it returned.

``openats discover verify`` reads this table. Each entry records one endpoint
that could plausibly enumerate ATS tenants, the method it was tried with, and
the verdict. ``LIVE`` sources are the only ones worth wiring into a discoverer.

Why this file exists
--------------------
Finding a company on a multi-tenant ATS means finding its tenant slug first,
and there is no public index of tenants for any of the ATSes openats
supports. The survey below covers every approach that could plausibly produce
one; almost all of them fail, and they fail in ways that are not obvious from
reading the vendor's documentation. Recording the dead ends here is the point
— re-probing them from scratch costs an afternoon.

Summary of the survey (verified 2026-10-25):

* **ATS-published feeds** — the only approach that works. JazzHR ships five
  unauthenticated XML shards listing its own tenants' jobs. No other supported
  ATS does anything equivalent.
* **Vendor "customers"/"case study" pages** — never contain tenant URLs.
  They link to vendor-owned subdomains (``app``, ``careers``, ``docs``,
  ``cdn``) and to customer logo images.
* **Vendor marketing sitemaps** — large (Breezy 10.5k URLs, Teamtailor 9.6k,
  SmartRecruiters 5.5k) but 100% vendor marketing pages.
* **Web search ``site:`` queries** — this is how the deleted
  ``services.discover.search`` module worked. Google returns a consent/JS
  wall, DuckDuckGo returns a 202 anomaly-detection page, and Bing returns 200
  with zero organic results (only links back to Bing's own verticals). All
  three were tested with a current browser User-Agent.
* **Certificate transparency** (crt.sh) — tenant domains use wildcard
  certificates, so the logs yield one base name instead of thousands, and the
  endpoint rate-limits into 502s under load.
* **Passive DNS enumeration** (HackerTarget) — returns the apex host only;
  tenants sit behind wildcard DNS.
* **Job aggregator APIs** — TheirStack is real and well-documented but needs
  a Bearer key; JobsPipe's documented endpoint is a 404; the no-key
  aggregators (Remotive, RemoteOK, Arbeitnow, Jobicy) contain zero URLs on
  supported ATS job domains in their payloads.

Adding to this table
--------------------
Probe with a browser User-Agent and record the *effective* outcome, not just
the status code — ``BLOCKED`` entries all return 200. ``LIVE`` is reserved
for endpoints that yielded tenant slugs.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum

from services._models import ATSType

#: Date every entry below was last probed.
SURVEY_DATE = "2026-10-25"

#: User-Agent used for the survey; several endpoints answer differently to a
#: default ``python-httpx`` UA.
SURVEY_USER_AGENT = (
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/120.0.0.0 Safari/537.36"
)


class SourceStatus(StrEnum):
    """Verdict for a probed discovery source."""

    #: Yields tenant slugs without credentials. The only status worth wiring up.
    LIVE = "live"
    #: A real, working endpoint that requires credentials we do not hold.
    AUTH_REQUIRED = "auth"
    #: Does not serve the payload it is documented to serve.
    DEAD = "dead"
    #: Returns 2xx but no usable payload (bot walls, CAPTCHAs, JS shells).
    BLOCKED = "blocked"
    #: Not yet probed.
    UNVERIFIED = "unverified"


class SourceKind(StrEnum):
    """What sort of endpoint it is."""

    FEED = "feed"
    AGGREGATOR = "aggregator"
    SEARCH = "search"
    DIRECTORY = "directory"
    ENUMERATION = "enumeration"


@dataclass(frozen=True)
class DiscoverySource:
    """One probed endpoint in the source survey."""

    label: str
    url: str
    kind: SourceKind
    status: SourceStatus
    notes: str
    #: ATS this source would feed, when the source is ATS-specific.
    ats: ATSType | None = None


SOURCES: tuple[DiscoverySource, ...] = (
    # --- LIVE ---------------------------------------------------------------
    DiscoverySource(
        label="JazzHR XML feed",
        url="https://app.jazz.co/feeds/google/xml/0",
        kind=SourceKind.FEED,
        status=SourceStatus.LIVE,
        notes="5 shards; the only unauthenticated tenant directory found. "
        "Backs JazzHRSitemapDiscovery.",
        ats=ATSType.JAZZHR,
    ),
    # --- AUTH_REQUIRED ------------------------------------------------------
    DiscoverySource(
        label="TheirStack API (real endpoint)",
        url="https://api.theirstack.com/openapi.json",
        kind=SourceKind.AGGREGATOR,
        status=SourceStatus.AUTH_REQUIRED,
        notes="POST /v1/jobs/search accepts url_domain_or "
        "(['jobs.lever.co','boards.greenhouse.io',...]) and returns job URLs "
        "the existing URL_PATTERN machinery can parse — one free key would "
        "feed ~13 ATS types. Unauthenticated calls return 401. "
        "Spec is public; the deleted aggregator.py pointed at the wrong host.",
    ),
    # --- DEAD ---------------------------------------------------------------
    DiscoverySource(
        label="TheirStack website search (as coded)",
        url="https://www.theirstack.com/api/v1/jobs/search",
        kind=SourceKind.AGGREGATOR,
        status=SourceStatus.DEAD,
        notes="307 redirect to the Next.js app shell, then HTML, not JSON. "
        "This was the URL TheirStackDiscovery posted to.",
    ),
    DiscoverySource(
        label="JobsPipe boards API",
        url="https://jobspipe.com/api/v1/boards",
        kind=SourceKind.AGGREGATOR,
        status=SourceStatus.DEAD,
        notes="404. This was the URL JobsPipeDiscovery got from.",
    ),
    DiscoverySource(
        label="crt.sh certificate transparency",
        url="https://crt.sh/?q=%25.jobs.lever.co&output=json",
        kind=SourceKind.ENUMERATION,
        status=SourceStatus.DEAD,
        notes="Tenant domains use wildcard certs, so the log yields one base "
        "name rather than thousands; the endpoint also 502s/timeouts.",
    ),
    DiscoverySource(
        label="HackerTarget passive DNS",
        url="https://api.hackertarget.com/hostsearch/?q=jobs.lever.co",
        kind=SourceKind.ENUMERATION,
        status=SourceStatus.DEAD,
        notes="Returns the apex host only — tenants sit behind wildcard DNS.",
    ),
    DiscoverySource(
        label="Lever case studies",
        url="https://www.lever.co/case-studies/",
        kind=SourceKind.DIRECTORY,
        status=SourceStatus.DEAD,
        notes="Representative of every vendor customer page probed (Ashby, "
        "Greenhouse, SmartRecruiters, Breezy, Pinpoint, BambooHR): "
        "vendor-owned subdomains only, no tenant URLs.",
    ),
    DiscoverySource(
        label="Ashby customers",
        url="https://ashbyhq.com/customers",
        kind=SourceKind.DIRECTORY,
        status=SourceStatus.DEAD,
        notes="2.9MB page; a single incidental jobs.ashbyhq.com link, not a directory.",
    ),
    DiscoverySource(
        label="iCIMS customer stories",
        url="https://www.icims.com/customers/",
        kind=SourceKind.DIRECTORY,
        status=SourceStatus.DEAD,
        notes="Representative of the careers.* host probe (Phenom, Avature, "
        "Teamtailor too): example/test hostnames and CDN assets only.",
    ),
    DiscoverySource(
        label="Teamtailor sitemap index",
        url="https://www.teamtailor.com/sitemap.xml",
        kind=SourceKind.DIRECTORY,
        status=SourceStatus.DEAD,
        notes="sitemapindex -> sitemap-0.xml holds 9,655 URLs, all "
        "www.teamtailor.com marketing pages. Same shape for Breezy, "
        "Pinpoint, Lever, SmartRecruiters, Recruitee, Personio.",
    ),
    DiscoverySource(
        label="Workday customer stories",
        url="https://www.workday.com/en-us/products/talent-management/customer-stories.html",
        kind=SourceKind.DIRECTORY,
        status=SourceStatus.DEAD,
        notes="No myworkdayjobs.com tenant URLs on the page.",
    ),
    DiscoverySource(
        label="Remotive jobs API",
        url="https://remotive.com/api/remote-jobs",
        kind=SourceKind.AGGREGATOR,
        status=SourceStatus.DEAD,
        notes="Free and keyless, but zero URLs on supported ATS job domains. "
        "Same for RemoteOK, Arbeitnow and Jobicy.",
    ),
    # --- BLOCKED -----------------------------------------------------------
    DiscoverySource(
        label="Google web search",
        url="https://www.google.com/search?q=site%3Ajobs.lever.co&num=100",
        kind=SourceKind.SEARCH,
        status=SourceStatus.BLOCKED,
        notes="200 with 0 organic result hrefs (consent/JS wall). This is what "
        "the deleted services.discover.search module called.",
    ),
    DiscoverySource(
        label="DuckDuckGo HTML endpoint",
        url="https://html.duckduckgo.com/html/?q=site%3Ajobs.lever.co",
        kind=SourceKind.SEARCH,
        status=SourceStatus.BLOCKED,
        notes="202 anomaly-detection page.",
    ),
    DiscoverySource(
        label="Bing web search",
        url="https://www.bing.com/search?q=site%3Ajobs.lever.co&count=50",
        kind=SourceKind.SEARCH,
        status=SourceStatus.BLOCKED,
        notes="200 but only links back to Bing's own verticals — no organic "
        "results for a site: query.",
    ),
    DiscoverySource(
        label="Personio job board",
        url="https://www.personio.com/job-board/",
        kind=SourceKind.DIRECTORY,
        status=SourceStatus.BLOCKED,
        notes="429 rate-limited from this network; jobs.personio.com refused "
        "the connection outright. Unresolved rather than disproven.",
    ),
)


def sources_by_status(status: SourceStatus) -> list[DiscoverySource]:
    """Every surveyed source with the given verdict, in survey order."""
    return [source for source in SOURCES if source.status is status]
