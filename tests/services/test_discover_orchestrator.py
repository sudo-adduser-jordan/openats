"""Orchestrator behaviour: dedup, database safety, and error isolation.

``discover_companies`` sits between unpredictable third-party feeds and a
local SQLite database, so the properties that matter are conservative ones:
never write a row we already have, never let one broken discoverer abort the
others, and never write at all when we cannot tell what is already stored.
"""

from __future__ import annotations

import asyncio
import logging
import sqlite3
from contextlib import nullcontext
from types import SimpleNamespace
from typing import Any

import pytest

import services.discover.discover as discover_module
from services._models import ATSType, Company
from services.discover import DiscoveryError
from services.discover._base import BaseDiscovery
from services.discover.discover import (
    _deduplicate,
    _load_existing_companies,
    _run_discoverer,
    _write_companies,
    discover_companies,
)

LOG = "services.discover.discover"


def _co(slug: str, ats: ATSType = ATSType.JAZZHR) -> Company:
    return Company(slug=slug, name=slug, ats=ats)


# --- fakes ----------------------------------------------------------------


class _FakeCursor:
    def __init__(self, rows: list[tuple[Any, ...]]) -> None:
        self._rows = rows

    def fetchall(self) -> list[tuple[Any, ...]]:
        return list(self._rows)


class _FakeConnection:
    def __init__(self, rows: list[tuple[Any, ...]], fail_on: set[str]) -> None:
        self._rows = rows
        self._fail_on = fail_on
        self.inserts: list[tuple[Any, ...]] = []

    def execute(self, sql: str, params: tuple[Any, ...] | None = None) -> _FakeCursor:
        if params is None:
            return _FakeCursor(self._rows)
        slug = params[2]  # INSERT_COMPANY binds (ats, name, slug, url)
        if slug in self._fail_on:
            raise sqlite3.IntegrityError(f"UNIQUE constraint failed: companies.{slug}")
        self.inserts.append(params)
        return _FakeCursor([])


class _FakeDatabase:
    """Stand-in for ``database.database.database`` so tests never touch disk."""

    def __init__(
        self,
        rows: list[tuple[Any, ...]] | None = None,
        *,
        fail_on: set[str] | None = None,
        down: bool = False,
    ) -> None:
        self.connection = _FakeConnection(rows or [], fail_on or set())
        self.down = down

    @property
    def inserts(self) -> list[tuple[Any, ...]]:
        return self.connection.inserts

    def connect(self):
        if self.down:
            raise sqlite3.OperationalError("unable to open database file")
        return nullcontext(self.connection)


def install_db(monkeypatch: pytest.MonkeyPatch, db: _FakeDatabase) -> _FakeDatabase:
    monkeypatch.setattr(discover_module, "database", db)
    return db


def make_discoverer(
    ats: ATSType,
    companies: list[Company],
    *,
    error: BaseException | None = None,
) -> type[BaseDiscovery]:
    async def discover(self: BaseDiscovery) -> list[Company]:
        if error is not None:
            raise error
        return list(companies)

    return type("_StubDiscoverer", (BaseDiscovery,), {"ats": ats, "discover": discover})


def install_roster(
    monkeypatch: pytest.MonkeyPatch,
    mapping: dict[ATSType, type[BaseDiscovery]],
) -> None:
    monkeypatch.setattr(
        discover_module, "DiscoveryRegistry", SimpleNamespace(all=lambda: dict(mapping))
    )
    monkeypatch.setattr(discover_module, "get_discoverer", lambda ats: mapping[ats]())


# --- _deduplicate ---------------------------------------------------------


def test_deduplicate_drops_slugs_already_in_the_database() -> None:
    existing = {"jazzhr": {"acme"}}
    out = _deduplicate([_co("acme"), _co("beta")], existing)
    assert [company.slug for company in out] == ["beta"]


def test_deduplicate_drops_repeats_from_the_same_run() -> None:
    out = _deduplicate([_co("acme"), _co("acme"), _co("beta")], {})
    assert [company.slug for company in out] == ["acme", "beta"]


def test_deduplicate_treats_the_same_slug_on_two_atses_as_distinct() -> None:
    out = _deduplicate([_co("acme", ATSType.JAZZHR), _co("acme", ATSType.GREENHOUSE)], {})
    assert [(c.ats, c.slug) for c in out] == [
        (ATSType.JAZZHR, "acme"),
        (ATSType.GREENHOUSE, "acme"),
    ]


def test_deduplicate_only_compares_within_the_matching_ats() -> None:
    existing = {"greenhouse": {"acme"}}
    out = _deduplicate([_co("acme", ATSType.JAZZHR)], existing)
    assert [company.slug for company in out] == ["acme"]


# --- _load_existing_companies --------------------------------------------


def test_load_existing_groups_slugs_by_ats(monkeypatch: pytest.MonkeyPatch) -> None:
    install_db(
        monkeypatch,
        _FakeDatabase(rows=[("jazzhr", "acme"), ("jazzhr", "beta"), ("greenhouse", "acme")]),
    )
    assert _load_existing_companies() == {
        "jazzhr": {"acme", "beta"},
        "greenhouse": {"acme"},
    }


def test_load_existing_returns_none_when_the_table_cannot_be_read(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    install_db(monkeypatch, _FakeDatabase(down=True))
    assert _load_existing_companies() is None


# --- _write_companies -----------------------------------------------------


def test_write_companies_inserts_every_row(monkeypatch: pytest.MonkeyPatch) -> None:
    db = install_db(monkeypatch, _FakeDatabase())
    assert _write_companies([_co("acme"), _co("beta")]) == 2
    assert [params[2] for params in db.inserts] == ["acme", "beta"]


def test_write_companies_skips_a_failing_row_without_aborting_the_batch(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    db = install_db(monkeypatch, _FakeDatabase(fail_on={"bad"}))
    assert _write_companies([_co("good"), _co("bad"), _co("ok")]) == 2
    assert [params[2] for params in db.inserts] == ["good", "ok"]


def test_write_companies_returns_zero_when_the_database_is_unavailable(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    install_db(monkeypatch, _FakeDatabase(down=True))
    assert _write_companies([_co("acme")]) == 0


def test_write_companies_short_circuits_on_empty_input(monkeypatch: pytest.MonkeyPatch) -> None:
    db = install_db(monkeypatch, _FakeDatabase())
    assert _write_companies([]) == 0
    assert db.inserts == []


# --- _run_discoverer ------------------------------------------------------


def test_run_discoverer_returns_results() -> None:
    discoverer = make_discoverer(ATSType.JAZZHR, [_co("acme")])
    out = asyncio.run(_run_discoverer(discoverer()))
    assert [company.slug for company in out] == ["acme"]


def test_run_discoverer_treats_discovery_error_as_a_warning(
    caplog: pytest.LogCaptureFixture,
) -> None:
    discoverer = make_discoverer(ATSType.JAZZHR, [], error=DiscoveryError("feed down"))
    with caplog.at_level(logging.WARNING, logger=LOG):
        assert asyncio.run(_run_discoverer(discoverer())) == []
    messages = [record.getMessage() for record in caplog.records]
    assert any("discover_failure" in message and "feed down" in message for message in messages)
    assert not any(record.exc_info for record in caplog.records)


def test_run_discoverer_logs_an_unexpected_crash_with_a_traceback(
    caplog: pytest.LogCaptureFixture,
) -> None:
    discoverer = make_discoverer(ATSType.JAZZHR, [], error=AttributeError("no attribute 'ats'"))
    with caplog.at_level(logging.ERROR, logger=LOG):
        assert asyncio.run(_run_discoverer(discoverer())) == []
    crash = [record for record in caplog.records if "discover_crashed" in record.getMessage()]
    assert crash, "an unexpected exception must be logged, not swallowed"
    assert crash[0].exc_info is not None


# --- discover_companies ---------------------------------------------------


def test_unregistered_ats_raises_before_touching_the_network(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    install_db(monkeypatch, _FakeDatabase())
    with pytest.raises(DiscoveryError, match="No discoverer registered for 'greenhouse'"):
        discover_companies(ats=ATSType.GREENHOUSE)


def test_discover_companies_dedups_and_writes(monkeypatch: pytest.MonkeyPatch) -> None:
    install_roster(
        monkeypatch,
        {
            ATSType.JAZZHR: make_discoverer(ATSType.JAZZHR, [_co("acme"), _co("beta")]),
            ATSType.GREENHOUSE: make_discoverer(
                ATSType.GREENHOUSE,
                [_co("beta", ATSType.GREENHOUSE), _co("gamma", ATSType.GREENHOUSE)],
            ),
        },
    )
    db = install_db(monkeypatch, _FakeDatabase(rows=[("jazzhr", "acme")]))

    out = discover_companies(write=True)

    # "acme" is already stored; "beta" appears twice because it is two
    # different companies on two different ATSes.
    assert [(c.ats, c.slug) for c in out] == [
        (ATSType.JAZZHR, "beta"),
        (ATSType.GREENHOUSE, "beta"),
        (ATSType.GREENHOUSE, "gamma"),
    ]
    assert [params[0] for params in db.inserts] == ["jazzhr", "greenhouse", "greenhouse"]


def test_dry_run_reports_without_writing(monkeypatch: pytest.MonkeyPatch) -> None:
    install_roster(
        monkeypatch, {ATSType.JAZZHR: make_discoverer(ATSType.JAZZHR, [_co("acme")])}
    )
    db = install_db(monkeypatch, _FakeDatabase())

    out = discover_companies(write=False)

    assert [company.slug for company in out] == ["acme"]
    assert db.inserts == []


def test_unreadable_companies_table_disables_writing(monkeypatch: pytest.MonkeyPatch) -> None:
    """We cannot tell new from known, so report but do not write."""
    install_roster(
        monkeypatch, {ATSType.JAZZHR: make_discoverer(ATSType.JAZZHR, [_co("acme")])}
    )
    db = install_db(monkeypatch, _FakeDatabase(down=True))

    out = discover_companies(write=True)

    assert [company.slug for company in out] == ["acme"]
    assert db.inserts == []


def test_one_crashing_discoverer_does_not_abort_the_run(
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
) -> None:
    install_roster(
        monkeypatch,
        {
            ATSType.JAZZHR: make_discoverer(
                ATSType.JAZZHR, [], error=AttributeError("no attribute 'ats'")
            ),
            ATSType.GREENHOUSE: make_discoverer(
                ATSType.GREENHOUSE, [_co("gamma", ATSType.GREENHOUSE)]
            ),
        },
    )
    install_db(monkeypatch, _FakeDatabase())

    with caplog.at_level(logging.ERROR, logger=LOG):
        out = discover_companies(write=True)

    assert [company.slug for company in out] == ["gamma"]


async def test_discover_companies_runs_from_an_already_running_loop(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """``asyncio.run`` refuses to nest, so the orchestrator must not either."""
    install_roster(
        monkeypatch, {ATSType.JAZZHR: make_discoverer(ATSType.JAZZHR, [_co("acme")])}
    )
    install_db(monkeypatch, _FakeDatabase())

    out = discover_companies(write=True)

    assert [company.slug for company in out] == ["acme"]


def test_discover_companies_with_no_registered_discoverers_returns_empty(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(discover_module, "DiscoveryRegistry", SimpleNamespace(all=lambda: {}))
    assert discover_companies() == []
