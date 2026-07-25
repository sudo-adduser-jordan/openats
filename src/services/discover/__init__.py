"""Company discovery infrastructure for openats.

This package provides automated discovery of companies across ATS platforms.
Discoverers register themselves with the ``DiscoveryRegistry`` and can be
run via the ``discover_companies()`` orchestrator.

>>> from services.discover import discover_companies
>>> new_companies = discover_companies(ats=ATSType.JAZZHR)
"""

from services.discover._base import BaseDiscovery, DiscoveryError, DiscoveryRegistry, get_discoverer
from services.discover.discover import discover_companies

__all__ = [
    "BaseDiscovery",
    "DiscoveryError",
    "DiscoveryRegistry",
    "discover_companies",
    "get_discoverer",
]
