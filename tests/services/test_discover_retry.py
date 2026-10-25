"""Retry behaviour of ``BaseDiscovery._fetch_with_retry``.

Discovery runs against third-party feeds that rate-limit and flap, so the
retry loop is the one piece of shared infrastructure every discoverer leans
on. These tests pin what is retried, how long we wait, and — just as
important — what fails fast instead of burning three attempts.
"""

from __future__ import annotations

import httpx
import pytest

from services._models import ATSType, Company
from services.discover import BaseDiscovery, DiscoveryError
from services.discover._base import _RETRYABLE_STATUSES

URL = "https://example.test/feed"


class _RetryDiscovery(BaseDiscovery):
    """Concrete discoverer with zero-length backoff so tests stay fast."""

    ats = ATSType.GREENHOUSE
    MAX_RETRIES = 3
    RETRY_BASE_DELAY = 0.0

    async def discover(self) -> list[Company]:
        return []


@pytest.fixture
def discoverer() -> _RetryDiscovery:
    return _RetryDiscovery()


async def test_success_is_returned_without_retry(discoverer, httpx_mock) -> None:
    httpx_mock.add_response(url=URL, text="<feed/>")

    async with httpx.AsyncClient() as client:
        response = await discoverer._fetch_with_retry(client, URL)

    assert response.status_code == 200
    assert response.text == "<feed/>"
    assert len(httpx_mock.get_requests()) == 1


async def test_transient_status_is_retried_then_succeeds(discoverer, httpx_mock) -> None:
    httpx_mock.add_response(url=URL, status_code=503)
    httpx_mock.add_response(url=URL, status_code=429, headers={"Retry-After": "0"})
    httpx_mock.add_response(url=URL, text="ok")

    async with httpx.AsyncClient() as client:
        response = await discoverer._fetch_with_retry(client, URL)

    assert response.text == "ok"
    assert len(httpx_mock.get_requests()) == 3


async def test_persistent_transient_status_exhausts_retries(discoverer, httpx_mock) -> None:
    for _ in range(discoverer.MAX_RETRIES):
        httpx_mock.add_response(url=URL, status_code=503)

    async with httpx.AsyncClient() as client:
        with pytest.raises(DiscoveryError, match="returned 503 after 3 retries"):
            await discoverer._fetch_with_retry(client, URL)

    assert len(httpx_mock.get_requests()) == discoverer.MAX_RETRIES


async def test_non_retryable_status_fails_immediately(discoverer, httpx_mock) -> None:
    httpx_mock.add_response(url=URL, status_code=404)

    async with httpx.AsyncClient() as client:
        with pytest.raises(DiscoveryError, match="returned 404"):
            await discoverer._fetch_with_retry(client, URL)

    # 404 means the feed is gone: retrying it three times helps nobody.
    assert len(httpx_mock.get_requests()) == 1


async def test_network_error_is_retried(discoverer, httpx_mock) -> None:
    httpx_mock.add_exception(httpx.ConnectError("connection reset"))
    httpx_mock.add_response(url=URL, text="recovered")

    async with httpx.AsyncClient() as client:
        response = await discoverer._fetch_with_retry(client, URL)

    assert response.text == "recovered"
    assert len(httpx_mock.get_requests()) == 2


async def test_persistent_network_error_reports_request_failure(discoverer, httpx_mock) -> None:
    for _ in range(discoverer.MAX_RETRIES):
        httpx_mock.add_exception(httpx.ConnectError("connection reset"))

    async with httpx.AsyncClient() as client:
        with pytest.raises(DiscoveryError, match=f"Request failed for {discoverer.ats.value}"):
            await discoverer._fetch_with_retry(client, URL)

    assert len(httpx_mock.get_requests()) == discoverer.MAX_RETRIES


def test_known_transient_statuses_are_retryable() -> None:
    # 403 is included because WAFs answer 403 to a fresh IP then let the
    # next attempt through; 404/410/401 are deliberately absent.
    assert _RETRYABLE_STATUSES == frozenset({403, 429, 502, 503, 504})
    assert 404 not in _RETRYABLE_STATUSES


def test_retry_after_seconds_is_honoured() -> None:
    response = httpx.Response(503, headers={"Retry-After": "7"})
    assert BaseDiscovery._retry_delay(response, base_delay=1.5, attempt=1) == 7.0


def test_retry_after_http_date_falls_back_to_backoff() -> None:
    response = httpx.Response(503, headers={"Retry-After": "Wed, 21 Oct 2026 07:28:00 GMT"})
    assert BaseDiscovery._retry_delay(response, base_delay=1.5, attempt=2) == 6.0


def test_missing_retry_after_falls_back_to_exponential_backoff() -> None:
    response = httpx.Response(503)
    assert BaseDiscovery._retry_delay(response, base_delay=1.5, attempt=1) == 3.0
    assert BaseDiscovery._retry_delay(response, base_delay=1.5, attempt=3) == 12.0
