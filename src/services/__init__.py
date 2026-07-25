"""openats services — collectors and company discovery.

Collectors: ``services.collect``
Discovery:  ``services.discover``
"""

from services._base import BaseCollector, CollectorRegistry, get_collector
from services.collect import *  # noqa: F403  — triggers all @register decorators

__all__ = [
    "BaseCollector",
    "CollectorRegistry",
    "get_collector",
]
