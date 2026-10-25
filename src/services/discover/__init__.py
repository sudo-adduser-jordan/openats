"""Company discovery infrastructure for openats.

This package provides automated discovery of companies across ATS platforms.
Discoverers register themselves with the ``DiscoveryRegistry`` and can be
run via the ``discover_companies()`` orchestrator.

>>> from services.discover import discover_companies
>>> new_companies = discover_companies(ats=ATSType.JAZZHR)
"""

# Discoverer modules are imported here so their @DiscoveryRegistry.register
# decorator runs. Adding a discoverer means adding an import to this block —
# one that is never imported never reaches the registry.
from services.discover import jazzhr  # noqa: F401  -- discoverer: registers jazzhr
from services.discover._base import (
    BaseDiscovery,
    DiscoveryError,
    DiscoveryRegistry,
    get_discoverer,
)
from services.discover._sources import SOURCES, DiscoverySource, SourceKind, SourceStatus
from services.discover.discover import discover_companies
from services.discover.sitemap import SitemapDiscovery

__all__ = [
    "SOURCES",
    "BaseDiscovery",
    "DiscoveryError",
    "DiscoveryRegistry",
    "DiscoverySource",
    "SitemapDiscovery",
    "SourceKind",
    "SourceStatus",
    "discover_companies",
    "get_discoverer",
]
