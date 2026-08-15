"""Tests for the database URL validation logic.

Validation must only remove rows whose URLs respond with 404/410 (Not
Found / Gone). Transient failures (timeouts, network errors, 5xx, 403)
and other statuses must be skipped, not deleted.
"""

from __future__ import annotations

import sqlite3

import httpx
import pytest

from database.database import Database

JOBS = [
    ("job-ok", "https://example.com/ok", "Software Engineer"),
    ("job-404", "https://example.com/missing", "Software Engineer"),
    ("job-410", "https://example.com/gone", "Software Engineer"),
    ("job-500", "https://example.com/error", "Software Engineer"),
    ("job-403", "https://example.com/blocked", "Software Engineer"),
    ("job-200-empty", "https://example.com/empty", "Software Engineer"),
]

COMPANIES = [
    ("acme-ok", "Acme", "acme", "https://acme.example.com"),
    ("acme-404", "Acme", "acme", "https://acme.example.com/missing"),
    ("acme-410", "Acme", "acme", "https://acme.example.com/gone"),
    ("acme-500", "Acme", "acme", "https://acme.example.com/error"),
    ("acme-403", "Acme", "acme", "https://acme.example.com/blocked"),
    ("acme-200-empty", "Acme", "acme", "https://acme.example.com/empty"),
]


class _FakeResponse:
    def __init__(self, status_code: int):
        self.status_code = status_code

    @property
    def is_success(self) -> bool:
        return 200 <= self.status_code < 300


@pytest.fixture
def jobs_connection(tmp_path):
    connection = sqlite3.connect(":memory:")
    connection.execute(
        "CREATE TABLE jobs (global_id TEXT, url TEXT, title TEXT)"
    )
    for _gid, url, title in JOBS:
        connection.execute(
            "INSERT INTO jobs (global_id, url, title) VALUES (?, ?, ?)",
            (_gid, url, title),
        )
    connection.commit()
    yield connection
    connection.close()


@pytest.fixture
def companies_connection(tmp_path):
    connection = sqlite3.connect(":memory:")
    connection.execute(
        "CREATE TABLE companies (rowid INTEGER PRIMARY KEY, name TEXT, slug TEXT, url TEXT)"
    )
    for _rid, name, slug, url in COMPANIES:
        connection.execute(
            "INSERT INTO companies (name, slug, url) VALUES (?, ?, ?)",
            (name, slug, url),
        )
    connection.commit()
    yield connection
    connection.close()


def _fake_get(monkeypatch: pytest.MonkeyPatch, statuses: dict[str, int]):
    def get(url, timeout=10.0, follow_redirects=True):
        for key, status in statuses.items():
            if key in url:
                return _FakeResponse(status)
        return _FakeResponse(200)

    monkeypatch.setattr(httpx, "get", get)


# --- Jobs -------------------------------------------------------------------


def test_job_urls_delete_only_404_410(monkeypatch, jobs_connection):
    _fake_get(
        monkeypatch,
        {
            "missing": 404,
            "gone": 410,
            "error": 500,
            "blocked": 403,
            "empty": 200,
        },
    )
    db = Database()
    passed, failed, skipped, total = db.validate_job_urls(
        jobs_connection, max_workers=4, dry_run=False
    )
    assert passed == 2
    assert failed == 2
    assert skipped == 2
    assert total == 6
    remaining = {row[0] for row in jobs_connection.execute("SELECT global_id FROM jobs")}
    assert remaining == {"job-ok", "job-500", "job-403", "job-200-empty"}


def test_job_urls_dry_run_deletes_nothing(monkeypatch, jobs_connection):
    _fake_get(monkeypatch, {"missing": 404, "gone": 410})
    db = Database()
    passed, failed, skipped, total = db.validate_job_urls(
        jobs_connection, max_workers=4, dry_run=True
    )
    assert (passed, failed, skipped, total) == (4, 0, 2, 6)
    remaining = {row[0] for row in jobs_connection.execute("SELECT global_id FROM jobs")}
    assert remaining == {gid for gid, _url, _title in JOBS}


def test_job_urls_skip_on_exception(monkeypatch, jobs_connection):
    def get(url, timeout=10.0, follow_redirects=True):
        raise httpx.ConnectTimeout("timed out", request=None)

    monkeypatch.setattr(httpx, "get", get)
    db = Database()
    passed, failed, skipped, total = db.validate_job_urls(
        jobs_connection, max_workers=4, dry_run=False
    )
    assert (passed, failed, skipped, total) == (0, 0, 6, 6)
    remaining = {row[0] for row in jobs_connection.execute("SELECT global_id FROM jobs")}
    assert remaining == {gid for gid, _url, _title in JOBS}


# --- Companies --------------------------------------------------------------


def test_company_urls_delete_only_404_410(monkeypatch, companies_connection):
    _fake_get(
        monkeypatch,
        {
            "missing": 404,
            "gone": 410,
            "error": 500,
            "blocked": 403,
            "empty": 200,
        },
    )
    db = Database()
    passed, failed, skipped, total = db.validate_company_urls(
        companies_connection, max_workers=4, dry_run=False
    )
    assert passed == 2
    assert failed == 2
    assert skipped == 2
    assert total == 6
    remaining = [row[0] for row in companies_connection.execute("SELECT rowid FROM companies")]
    assert remaining == [1, 4, 5, 6]


def test_company_urls_dry_run_deletes_nothing(monkeypatch, companies_connection):
    _fake_get(monkeypatch, {"missing": 404, "gone": 410})
    db = Database()
    passed, failed, skipped, total = db.validate_company_urls(
        companies_connection, max_workers=4, dry_run=True
    )
    assert (passed, failed, skipped, total) == (4, 0, 2, 6)
    remaining = [row[0] for row in companies_connection.execute("SELECT rowid FROM companies")]
    assert remaining == [1, 2, 3, 4, 5, 6]


def test_company_urls_skip_on_exception(monkeypatch, companies_connection):
    def get(url, timeout=10.0, follow_redirects=True):
        raise httpx.ReadTimeout("timed out", request=None)

    monkeypatch.setattr(httpx, "get", get)
    db = Database()
    passed, failed, skipped, total = db.validate_company_urls(
        companies_connection, max_workers=4, dry_run=False
    )
    assert (passed, failed, skipped, total) == (0, 0, 6, 6)
    remaining = [row[0] for row in companies_connection.execute("SELECT rowid FROM companies")]
    assert remaining == [1, 2, 3, 4, 5, 6]
