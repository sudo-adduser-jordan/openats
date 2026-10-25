"""Live probing of the discovery source survey.

Backs ``openats discover verify``. Each :class:`DiscoverySource` from
``_sources`` is fetched and reported alongside its recorded verdict, so a
source can be re-checked after the survey date without re-deriving the list.
"""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass

import httpx

from services.discover._base import DiscoveryRegistry
from services.discover._sources import (
    SOURCES,
    SURVEY_DATE,
    SURVEY_USER_AGENT,
    DiscoverySource,
    SourceStatus,
)

#: The recorded verdict a source must hold to be considered worth protecting
#: with a live probe.
_ACTIONABLE = (SourceStatus.LIVE, SourceStatus.AUTH_REQUIRED)


@dataclass(frozen=True)
class ProbeResult:
    """A surveyed source plus (optionally) its live HTTP outcome."""

    source: DiscoverySource
    http_status: int | None = None
    error: str | None = None

    @property
    def registered(self) -> bool:
        """Whether a discoverer is currently registered for this source's ATS."""
        if self.source.ats is None:
            return False
        return self.source.ats in DiscoveryRegistry.all()

    @property
    def probed(self) -> bool:
        """Whether a request was actually attempted (offline runs do not)."""
        return self.http_status is not None or self.error is not None

    @property
    def reachable(self) -> bool:
        """True when the endpoint answered at all (any status code)."""
        return self.http_status is not None


def probe_sources(
    sources: Iterable[DiscoverySource] = SOURCES,
    *,
    timeout: float = 15.0,
    offline: bool = False,
) -> list[ProbeResult]:
    """Fetch every source URL and pair the outcome with its recorded verdict.

    ``offline`` skips the network entirely and returns the survey as recorded.
    A transport failure is reported rather than raised: half the survey is
    expected to be unreachable, and one dead host must not abort the run.
    """
    results: list[ProbeResult] = []
    if offline:
        return [ProbeResult(source=source) for source in sources]

    with httpx.Client(
        timeout=timeout,
        follow_redirects=True,
        headers={"User-Agent": SURVEY_USER_AGENT, "Accept": "*/*"},
    ) as client:
        for source in sources:
            try:
                response = client.get(source.url)
            except httpx.HTTPError as exc:
                results.append(ProbeResult(source=source, error=f"{type(exc).__name__}: {exc}"))
                continue
            results.append(ProbeResult(source=source, http_status=response.status_code))
    return results


def format_report(results: Iterable[ProbeResult], *, verbose: bool = False) -> str:
    """Render probe results as a fixed-width table plus a summary line."""
    rows = list(results)
    header = f"{'STATUS':<11} {'KIND':<13} {'ATS':<20} {'HTTP':<7} {'IN REGISTRY':<12} SOURCE"
    lines = [header, "-" * len(header)]

    for result in rows:
        source = result.source
        if result.http_status is not None:
            http = str(result.http_status)
        elif result.error:
            http = _truncate(result.error, 7)
        else:
            http = "skipped"
        lines.append(
            f"{source.status.value:<11} "
            f"{source.kind.value:<13} "
            f"{(source.ats.value if source.ats else '-'):<20} "
            f"{http:<7} "
            f"{('yes' if result.registered else 'no'):<12} "
            f"{source.label}"
        )
        if verbose:
            lines.append(f"{'':11} {source.url}")
            lines.append(f"{'':11} {source.notes}")

    counts: dict[SourceStatus, int] = {}
    for result in rows:
        counts[result.source.status] = counts.get(result.source.status, 0) + 1
    summary = ", ".join(
        f"{counts[status]} {status.value}" for status in SourceStatus if status in counts
    )
    lines.append("")
    lines.append(f"{len(rows)} sources surveyed ({summary})")
    lines.append(f"Survey recorded {SURVEY_DATE}")
    return "\n".join(lines)


def _truncate(text: str, width: int) -> str:
    return text if len(text) <= width else text[: width - 1] + "…"


def unreachable_required(results: Iterable[ProbeResult]) -> list[ProbeResult]:
    """Actionable sources that were probed but never answered.

    These are the only failures worth reporting — the rest of the survey being
    unreachable is the expected state, and offline runs are not probed at all.
    """
    return [
        result
        for result in results
        if result.source.status in _ACTIONABLE and result.probed and not result.reachable
    ]
