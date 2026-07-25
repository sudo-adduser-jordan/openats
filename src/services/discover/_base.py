"""Base class and registry for ATS company discoverers.

Adding a new discoverer:

    from services.discover._base import BaseDiscovery, DiscoveryRegistry
    from services._models import ATSType

    @DiscoveryRegistry.register(ATSType.GREENHOUSE)
    class GreenhouseDiscovery(BaseDiscovery):
        ats = ATSType.GREENHOUSE

        async def discover(self) -> list[Company]:
            ...

The registry is the only stable lookup mechanism — never import discoverer
classes by path from outside the package.
"""

from __future__ import annotations

import asyncio
import logging
from abc import ABC, abstractmethod
from typing import TYPE_CHECKING, Any, ClassVar

import httpx

from exceptions import AtsCollectorError
from services._models import ATSType

if TYPE_CHECKING:
    from collections.abc import Callable

    from services._models import Company

log = logging.getLogger(__name__)

_RETRYABLE_STATUSES: frozenset[int] = frozenset({403, 429, 502, 503, 504})


class DiscoveryError(AtsCollectorError):
    """Raised when a company discovery operation fails."""


class BaseDiscovery(ABC):
    """Abstract base for every ATS company discoverer.

    Subclasses must set the ``ats`` class attribute and implement ``discover()``.

    Shared infrastructure provided by the base class:

    * :meth:`_fetch_with_retry` — HTTP GET with exponential backoff,
      ``Retry-After`` header support, and configurable retryable status codes.
    """

    ats: ClassVar[ATSType]
    MAX_RETRIES: ClassVar[int] = 3
    RETRY_BASE_DELAY: ClassVar[float] = 1.5

    def __init__(self, *, timeout: float = 30.0) -> None:
        self.timeout = timeout

    @abstractmethod
    async def discover(self) -> list[Company]:
        """Discover companies on this ATS and return them."""

    async def _fetch_with_retry(
        self,
        client: httpx.AsyncClient,
        url: str,
        *,
        headers: dict[str, str] | None = None,
        params: dict[str, Any] | None = None,
        max_retries: int | None = None,
        retry_base_delay: float | None = None,
        retryable_statuses: frozenset[int] = _RETRYABLE_STATUSES,
    ) -> httpx.Response:
        """Make an HTTP GET request with retries on transient failures."""
        if max_retries is None:
            max_retries = self.MAX_RETRIES
        if retry_base_delay is None:
            retry_base_delay = self.RETRY_BASE_DELAY
        last_exc: Exception | None = None
        last_status: int | None = None
        for attempt in range(1, max_retries + 1):
            try:
                response = await client.get(url, headers=headers, params=params)
            except httpx.HTTPError as exc:
                last_exc = exc
                if attempt == max_retries:
                    raise DiscoveryError(f"Request failed for {self.ats.value}: {exc}") from exc
                await asyncio.sleep(retry_base_delay * attempt)
                continue

            if response.status_code == 200:
                return response

            if response.status_code in retryable_statuses or (500 <= response.status_code < 600):
                last_status = response.status_code
                if attempt == max_retries:
                    raise DiscoveryError(
                        f"{self.ats.value} returned {response.status_code} "
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

            raise DiscoveryError(f"{self.ats.value} returned {response.status_code}")

        raise DiscoveryError(
            f"{self.ats.value} exhausted retries: {last_exc or f'HTTP {last_status}' or 'unknown'}"
        )

    def __repr__(self) -> str:
        return f"{self.__class__.__name__}(ats={self.ats.value!r})"


class DiscoveryRegistry:
    """Maps ``ATSType`` → discoverer class.

    Filled at import time via the ``@register`` decorator. Use ``get_discoverer``
    to look up a discoverer by ATS.
    """

    _discoverers: ClassVar[dict[ATSType, type[BaseDiscovery]]] = {}

    @classmethod
    def register(cls, ats: ATSType) -> Callable[[type[BaseDiscovery]], type[BaseDiscovery]]:
        def decorator(discoverer_cls: type[BaseDiscovery]) -> type[BaseDiscovery]:
            cls._discoverers[ats] = discoverer_cls
            return discoverer_cls

        return decorator

    @classmethod
    def get(cls, ats: ATSType | str) -> type[BaseDiscovery]:
        ats_enum = ATSType(ats) if isinstance(ats, str) else ats
        try:
            return cls._discoverers[ats_enum]
        except KeyError as exc:
            raise DiscoveryError(
                f"No discoverer registered for {ats_enum.value!r}. "
                f"Available: {sorted(s.value for s in cls._discoverers)}"
            ) from exc

    @classmethod
    def all(cls) -> dict[ATSType, type[BaseDiscovery]]:
        return dict(cls._discoverers)


def get_discoverer(ats: ATSType | str, **kwargs: object) -> BaseDiscovery:
    """Convenience: lookup + instantiate in one step."""
    return DiscoveryRegistry.get(ats)(**kwargs)  # type: ignore[arg-type]
