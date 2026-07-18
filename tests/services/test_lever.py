"""Tests for the Lever collector."""

from __future__ import annotations

import pytest

from exceptions import CompanyNotFoundError
from services import CollectorRegistry, LeverCollector
from services._models import ATSType

API = "https://api.lever.co/v0/postings/acme?mode=json"


@pytest.fixture(autouse=True)
def _fast_retries(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(LeverCollector, "MAX_RETRIES", 1)
    monkeypatch.setattr(LeverCollector, "RETRY_BASE_DELAY", 0.0)


def _job(jid: str = "x1", text: str = "SWE",
         location: str = "Remote") -> dict:
    return {
        "id": jid,
        "text": text,
        "hostedUrl": f"https://jobs.lever.co/acme/{jid}",
        "categories": {"location": location, "team": "Eng"},
        "createdAt": 1714521600000,  # ~2026-04-30
    }


def test_registry_resolves_lever() -> None:
    assert CollectorRegistry.get(ATSType.LEVER) is LeverCollector


def test_parses_basic_job(httpx_mock) -> None:
    httpx_mock.add_response(url=API, json=[_job()])
    jobs = LeverCollector("acme").fetch()
    assert len(jobs) == 1
    job = jobs[0]
    assert job.title == "SWE"
    assert job.company == "acme"
    assert job.location == "Remote"
    assert job.ats_id == "x1"


def test_returns_empty_list(httpx_mock) -> None:
    httpx_mock.add_response(url=API, json=[])
    assert LeverCollector("acme").fetch() == []


def test_404_company_not_found(httpx_mock) -> None:
    httpx_mock.add_response(url=API, status_code=404)
    with pytest.raises(CompanyNotFoundError):
        LeverCollector("acme").fetch()


def test_5xx_retries(monkeypatch, httpx_mock) -> None:
    monkeypatch.setattr(LeverCollector, "MAX_RETRIES", 3)
    httpx_mock.add_response(url=API, status_code=502)
    httpx_mock.add_response(url=API, json=[_job()])
    assert len(LeverCollector("acme").fetch()) == 1
