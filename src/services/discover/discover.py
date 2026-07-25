"""Company discovery orchestrator.

Runs registered discoverers, deduplicates against the existing companies
table, and optionally writes new companies directly to the database.
"""

from __future__ import annotations

import asyncio
import logging
from typing import TYPE_CHECKING

from database.database import INSERT_COMPANY, database
from services._models import ATSType, Company
from services.discover._base import BaseDiscovery, DiscoveryError, DiscoveryRegistry

if TYPE_CHECKING:
    pass

log = logging.getLogger(__name__)


async def _run_discoverer(discoverer: BaseDiscovery) -> list[Company]:
    """Run a single discoverer and return its results."""
    try:
        companies = await discoverer.discover()
        log.info(
            "discover_result ats=%s companies=%d",
            discoverer.ats.value,
            len(companies),
        )
        return companies
    except DiscoveryError as exc:
        log.error(
            "discover_failure ats=%s error=%s",
            discoverer.ats.value,
            exc,
        )
        return []
    except Exception as exc:
        log.error(
            "discover_failure ats=%s error=%s",
            discoverer.ats.value,
            exc,
        )
        return []


def _deduplicate(
    discovered: list[Company],
    existing: dict[str, set[str]],
) -> list[Company]:
    """Filter out companies already in the database.

    ``existing`` maps ``ats_type`` → set of slugs.
    """
    new_companies: list[Company] = []
    for company in discovered:
        if company.ats.value not in existing or company.slug not in existing[company.ats.value]:
            new_companies.append(company)
    return new_companies


def _load_existing_companies() -> dict[str, set[str]]:
    """Load existing company slugs from the database, grouped by ATS type."""
    existing: dict[str, set[str]] = {}
    try:
        with database.connect() as connection:
            rows = connection.execute("SELECT ats, slug FROM companies").fetchall()
            for ats_type, slug in rows:
                if ats_type not in existing:
                    existing[ats_type] = set()
                existing[ats_type].add(slug)
    except Exception as exc:
        log.warning("load_existing_companies error=%s", exc)
    return existing


def _write_companies(companies: list[Company]) -> int:
    """Insert companies into the database. Returns the number inserted."""
    if not companies:
        return 0
    inserted = 0
    try:
        with database.connect() as connection:
            for company in companies:
                try:
                    connection.execute(
                        INSERT_COMPANY,
                        (
                            company.ats.value,
                            company.name,
                            company.slug,
                            str(company.careers_url or ""),
                        ),
                    )
                    inserted += 1
                except Exception as exc:
                    log.warning(
                        "insert_company ats=%s slug=%s error=%s",
                        company.ats.value,
                        company.slug,
                        exc,
                    )
    except Exception as exc:
        log.error("write_companies error=%s", exc)
    return inserted


def discover_companies(
    ats: ATSType | None = None,
    write: bool = True,
) -> list[Company]:
    """Discover companies across registered discoverers.

    Args:
        ats: If provided, only run discoverers for this ATS type.
        write: If True, insert new companies into the database.

    Returns:
        List of newly discovered companies (not already in DB).
    """
    # Import all discoverers to trigger @register decorators
    import services.discover.jazzhr  # noqa: F401

    # Get discoverers to run
    if ats is not None:
        discoverers = {ats: DiscoveryRegistry.get(ats)()}
    else:
        discoverers = {ats_type: cls() for ats_type, cls in DiscoveryRegistry.all().items()}

    if not discoverers:
        log.warning("discover_no_discoverers")
        return []

    # Run all discoverers concurrently
    async def _run_all() -> list[Company]:
        tasks = [_run_discoverer(d) for d in discoverers.values()]
        results = await asyncio.gather(*tasks)
        return [c for batch in results for c in batch]

    all_discovered = asyncio.run(_run_all())

    # Deduplicate against existing companies
    existing = _load_existing_companies()
    new_companies = _deduplicate(all_discovered, existing)

    log.info(
        "discover_summary total_discovered=%d new_companies=%d write=%s",
        len(all_discovered),
        len(new_companies),
        write,
    )

    # Write to database if requested
    if write and new_companies:
        inserted = _write_companies(new_companies)
        log.info("discover_written inserted=%d", inserted)

    return new_companies
