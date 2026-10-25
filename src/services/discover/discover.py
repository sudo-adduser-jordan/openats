"""Company discovery orchestrator.

Runs registered discoverers, deduplicates against the existing companies
table, and optionally writes new companies directly to the database.

Registration is *not* handled here: importing a discoverer module runs its
``@DiscoveryRegistry.register`` decorator, and ``services.discover.__init__``
owns that import list. Callers should ``import services.discover`` (or any of
its public names) rather than importing this module directly.
"""

from __future__ import annotations

import asyncio
import logging
from collections.abc import Coroutine, Iterable
from concurrent.futures import ThreadPoolExecutor

from database.database import INSERT_COMPANY, database
from services._models import ATSType, Company
from services.discover._base import BaseDiscovery, DiscoveryError, DiscoveryRegistry, get_discoverer

log = logging.getLogger(__name__)


async def _run_discoverer(discoverer: BaseDiscovery) -> list[Company]:
    """Run a single discoverer and return its results.

    A :class:`DiscoveryError` is an expected per-ATS condition — the source is
    down, rate-limiting, or blocking us — so it is logged as a warning and the
    other discoverers keep running. Anything else is a bug in the discoverer
    and is logged with a traceback so it does not hide behind a tidy message.
    """
    ats = discoverer.ats.value
    try:
        companies = await discoverer.discover()
    except DiscoveryError as exc:
        log.warning("discover_failure ats=%s error=%s", ats, exc)
        return []
    except Exception:  # pylint: disable=broad-exception-caught
        # Deliberately broad: a discoverer raising anything other than
        # DiscoveryError is a bug, and one broken discoverer must not abort
        # the others. log.exception keeps the traceback visible.
        log.exception("discover_crashed ats=%s", ats)
        return []
    log.info("discover_result ats=%s companies=%d", ats, len(companies))
    return companies


def _deduplicate(
    discovered: list[Company],
    existing: dict[str, set[str]],
) -> list[Company]:
    """Filter out companies already in the database or already seen this run.

    ``existing`` maps ``ats_type`` → set of slugs. The first occurrence of a
    ``(ats, slug)`` pair wins, both against the database and across
    discoverers: two discoverers may well surface the same company, and the
    ``companies`` table has no unique constraint to fall back on.
    """
    new_companies: list[Company] = []
    seen: set[tuple[str, str]] = set()
    for company in discovered:
        key = (company.ats.value, company.slug)
        if key in seen:
            continue
        known = existing.get(company.ats.value)
        if known is not None and company.slug in known:
            continue
        seen.add(key)
        new_companies.append(company)
    return new_companies


def _load_existing_companies() -> dict[str, set[str]] | None:
    """Load existing company slugs from the database, grouped by ATS type.

    Returns ``None`` when the table cannot be read. Callers must treat that as
    "we do not know what is already stored" and skip writing, rather than
    assume the table is empty and insert duplicates.
    """
    existing: dict[str, set[str]] = {}
    try:
        with database.connect() as connection:
            rows = connection.execute("SELECT ats, slug FROM companies").fetchall()
    except Exception as exc:  # pylint: disable=broad-exception-caught
        log.error("load_existing_companies error=%s", exc)
        return None
    for ats_type, slug in rows:
        existing.setdefault(ats_type, set()).add(slug)
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
                except Exception as exc:  # pylint: disable=broad-exception-caught
                    # One malformed row must not sink the whole batch.
                    log.warning(
                        "insert_company ats=%s slug=%s error=%s",
                        company.ats.value,
                        company.slug,
                        exc,
                    )
    except Exception as exc:  # pylint: disable=broad-exception-caught
        # Connection-level failure: report 0 rather than a partial count the
        # caller would otherwise treat as success.
        log.error("write_companies error=%s", exc)
        return 0
    return inserted


def _run_coroutine(coro: Coroutine[object, object, list[Company]]) -> list[Company]:
    """Run ``coro`` to completion from either a sync or an already-running loop.

    ``asyncio.run`` refuses to nest inside a live event loop, so when we are
    called from async code we hand the coroutine to a worker thread that owns
    its own loop. Exceptions propagate to the caller either way.
    """
    try:
        asyncio.get_running_loop()
    except RuntimeError:
        return asyncio.run(coro)
    with ThreadPoolExecutor(max_workers=1) as pool:
        return pool.submit(asyncio.run, coro).result()


async def _run_all(discoverers: Iterable[BaseDiscovery]) -> list[Company]:
    results = await asyncio.gather(*(_run_discoverer(d) for d in discoverers))
    return [company for batch in results for company in batch]


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

    Raises:
        DiscoveryError: If ``ats`` names an ATS with no registered discoverer,
            or names something that is not an ATS type at all.
    """
    # Building the mapping instantiates the discoverer, so an unregistered ATS
    # raises DiscoveryError here — before any network traffic.
    if ats is not None:
        discoverers: dict[ATSType, BaseDiscovery] = {ats: get_discoverer(ats)}
    else:
        discoverers = {ats_type: cls() for ats_type, cls in DiscoveryRegistry.all().items()}

    if not discoverers:
        log.warning("discover_no_discoverers")
        return []

    all_discovered = _run_coroutine(_run_all(discoverers.values()))

    existing = _load_existing_companies()
    if existing is None:
        # We cannot tell stored companies from new ones, so report everything
        # we found but refuse to write.
        existing = {}
        if write:
            log.error("discover_existing_companies_unreadable write_disabled")
        write = False

    new_companies = _deduplicate(all_discovered, existing)

    log.info(
        "discover_summary total_discovered=%d new_companies=%d write=%s",
        len(all_discovered),
        len(new_companies),
        write,
    )

    if write and new_companies:
        inserted = _write_companies(new_companies)
        log.info("discover_written inserted=%d", inserted)

    return new_companies
