"""Base class and registry for ATS collectors.

Adding a new collector:

    from services._base import BaseCollector, CollectorRegistry
    from services._models import ATSType, Job

    @CollectorRegistry.register(ATSType.GREENHOUSE)
    class GreenhouseCollector(BaseCollector):
        ats = ATSType.GREENHOUSE

        def fetch(self) -> list[Job]:
            ...

The registry is the only stable lookup mechanism — never import collector
classes by path from outside the package.
"""

from __future__ import annotations

import asyncio
import logging
from abc import ABC, abstractmethod
from typing import TYPE_CHECKING, Any, ClassVar

import httpx

from exceptions import CollectorError, CompanyNotFoundError
from services._models import ATSType

if TYPE_CHECKING:
    from collections.abc import Callable

    from services._models import Job

log = logging.getLogger(__name__)


def _json(response: httpx.Response) -> dict[str, Any]:
    """Typed wrapper around ``response.json()`` to avoid ``no-any-return``."""
    return response.json()


# Default retryable status codes shared across collectors.  Collectors that
# need a different set pass ``retryable_statuses`` explicitly.
_RETRYABLE_STATUSES: frozenset[int] = frozenset({403, 429, 502, 503, 504})


class BaseCollector(ABC):
    """Abstract base for every ATS collector.

    Subclasses must set the ``ats`` class attribute and implement ``fetch()``.

    Shared infrastructure provided by the base class:

    * :meth:`_fetch_with_retry` — HTTP GET/POST with exponential backoff,
      ``Retry-After`` header support, and configurable retryable status codes.
      Covers the standard retry pattern used by ~30 collectors.  Collectors
      with unique retry behaviour (jitter, deadlines, partial results, …)
      override with their own implementation.
    """

    ats: ClassVar[ATSType]
    MAX_RETRIES: ClassVar[int] = 3
    RETRY_BASE_DELAY: ClassVar[float] = 1.5

    def __init__(self, company_slug: str, *, timeout: float = 30.0, url: str | None = None) -> None:
        self.company_slug = company_slug
        self.url = url or company_slug
        self.timeout = timeout
        self.include_descriptions = True

    @abstractmethod
    def fetch(self) -> list[Job]:
        """Return all currently active jobs for this company."""

    # ------------------------------------------------------------------
    # Shared retry helper
    # ------------------------------------------------------------------

    async def _fetch_with_retry(
        self,
        client: httpx.AsyncClient,
        url: str,
        *,
        method: str = "GET",
        headers: dict[str, str] | None = None,
        json_body: dict[str, Any] | None = None,
        params: dict[str, Any] | None = None,
        max_retries: int | None = None,
        retry_base_delay: float | None = None,
        retryable_statuses: frozenset[int] = _RETRYABLE_STATUSES,
        not_found_error: type[Exception] | None = CompanyNotFoundError,
    ) -> httpx.Response:
        """Make an HTTP request with retries on transient failures.

        Returns the :class:`httpx.Response` on success (status 200).

        Behaviour on specific status codes:

        * **200** — return the response.
        * **404** — raise *not_found_error* (or return the response if
          ``not_found_error`` is ``None``).
        * **429 / 5xx in *retryable_statuses*** — exponential backoff with
          ``Retry-After`` header support.
        * **Other** — raise :class:`CollectorError`.

        Network errors (``httpx.HTTPError``) are retried with linear backoff.
        """
        if max_retries is None:
            max_retries = self.MAX_RETRIES
        if retry_base_delay is None:
            retry_base_delay = self.RETRY_BASE_DELAY
        last_exc: Exception | None = None
        last_status: int | None = None
        for attempt in range(1, max_retries + 1):
            try:
                if method.upper() == "POST":
                    response = await client.post(
                        url,
                        json=json_body,
                        headers=headers,
                        params=params,
                    )
                else:
                    response = await client.get(url, headers=headers, params=params)
            except httpx.HTTPError as exc:
                last_exc = exc
                if attempt == max_retries:
                    raise CollectorError(f"Request failed for {self.company_slug}: {exc}") from exc
                await asyncio.sleep(retry_base_delay * attempt)
                continue

            if response.status_code == 200:
                return response

            if response.status_code == 404:
                if not_found_error is None:
                    return response
                raise not_found_error(f"Resource not found for {self.company_slug}")

            if response.status_code in retryable_statuses or (500 <= response.status_code < 600):
                last_status = response.status_code
                if attempt == max_retries:
                    raise CollectorError(
                        f"{self.company_slug} returned {response.status_code} "
                        f"after {max_retries} retries"
                    )
                retry_after = response.headers.get("Retry-After")
                if retry_after:
                    try:
                        delay = float(retry_after)
                    except ValueError:
                        delay = retry_base_delay * (2**attempt)
                else:
                    delay = retry_base_delay * (2**attempt)
                await asyncio.sleep(delay)
                continue

            raise CollectorError(f"{self.company_slug} returned {response.status_code}")

        raise CollectorError(
            f"{self.company_slug} exhausted retries: "
            f"{last_exc or f'HTTP {last_status}' or 'unknown'}"
        )

    # ------------------------------------------------------------------
    # Description enrichment
    # ------------------------------------------------------------------

    def get_description(self, job: Job) -> str | None:
        """Fetch or return the best-known description for one job.

        The default implementation is correct for providers whose listing
        payload already includes the full description. Providers that need a
        per-job detail request override this method.
        """
        return job.description

    def enrich_descriptions(self, jobs: list[Job]) -> list[Job]:
        """Fill missing descriptions in ``jobs`` when the provider supports it.

        The default path calls :meth:`get_description` one job at a time.
        High-volume providers can override this with a batched/concurrent
        implementation while keeping the public API stable.
        """
        for job in jobs:
            if job.description:
                continue
            description = self.get_description(job)
            if description:
                job.description = description[:25_000]
        return jobs

    def __repr__(self) -> str:
        return f"{self.__class__.__name__}({self.company_slug!r})"


class CollectorRegistry:
    """Maps ``ATSType`` → collector class.

    Filled at import time via the ``@register`` decorator. Use ``get_collector``
    to look up a collector by ATS.
    """

    _collectors: ClassVar[dict[ATSType, type[BaseCollector]]] = {}

    @classmethod
    def register(cls, ats: ATSType) -> Callable[[type[BaseCollector]], type[BaseCollector]]:
        def decorator(collector_cls: type[BaseCollector]) -> type[BaseCollector]:
            cls._collectors[ats] = collector_cls
            return collector_cls

        return decorator

    @classmethod
    def get(cls, ats: ATSType | str) -> type[BaseCollector]:
        ats_enum = ATSType(ats) if isinstance(ats, str) else ats
        try:
            return cls._collectors[ats_enum]
        except KeyError as exc:
            raise CollectorError(
                f"No collector registered for {ats_enum.value!r}. "
                f"Available: {sorted(s.value for s in cls._collectors)}"
            ) from exc

    @classmethod
    def all(cls) -> dict[ATSType, type[BaseCollector]]:
        return dict(cls._collectors)


def get_collector(ats: ATSType | str, company_slug: str, **kwargs: object) -> BaseCollector:
    """Convenience: lookup + instantiate in one step."""
    return CollectorRegistry.get(ats)(company_slug, **kwargs)  # type: ignore[arg-type]
