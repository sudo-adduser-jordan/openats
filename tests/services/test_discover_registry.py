"""Registry behaviour for the company-discovery package.

The registry is the only lookup mechanism discoverers have, so these tests
pin the two invariants that are easy to break silently: a discoverer must
expose ``ats`` (the orchestrator reads it while logging), and registering the
same ATS twice must fail rather than silently overwrite.
"""

from __future__ import annotations

import pytest

from services._models import ATSType, Company
from services.discover import (
    BaseDiscovery,
    DiscoveryError,
    DiscoveryRegistry,
    SitemapDiscovery,
    get_discoverer,
)
from services.discover.jazzhr import JAZZHR_FEED_URLS


def test_jazzhr_is_registered() -> None:
    assert ATSType.JAZZHR in DiscoveryRegistry.all()
    assert DiscoveryRegistry.get(ATSType.JAZZHR).__name__ == "JazzHRSitemapDiscovery"


def test_every_registered_discoverer_exposes_ats_and_repr() -> None:
    """The orchestrator reads ``.ats`` and ``repr()`` reads it too.

    Before this was enforced, subclasses set ``ATS_TYPE`` instead, every
    discoverer raised AttributeError at run time, and discovery returned
    nothing at all.
    """
    assert DiscoveryRegistry.all(), "registry should not be empty"
    for ats, discoverer_cls in DiscoveryRegistry.all().items():
        instance = discoverer_cls()
        assert instance.ats is ats
        assert repr(instance) == f"{discoverer_cls.__name__}(ats={ats.value!r})"


def test_get_accepts_enum_and_string() -> None:
    assert DiscoveryRegistry.get("jazzhr") is DiscoveryRegistry.get(ATSType.JAZZHR)


def test_get_unregistered_ats_raises_discovery_error() -> None:
    with pytest.raises(DiscoveryError, match="No discoverer registered for 'greenhouse'"):
        DiscoveryRegistry.get(ATSType.GREENHOUSE)


def test_get_mistyped_ats_raises_discovery_error_not_value_error() -> None:
    """A typo must produce the package's own error, with the valid types."""
    with pytest.raises(DiscoveryError, match="Unknown ATS type 'not-an-ats'"):
        DiscoveryRegistry.get("not-an-ats")


def test_get_discoverer_instantiates_with_source_url() -> None:
    discoverer = get_discoverer("jazzhr")
    assert isinstance(discoverer, SitemapDiscovery)
    assert discoverer.timeout == 30.0
    assert discoverer.SOURCE_URL == JAZZHR_FEED_URLS[0]


def test_duplicate_registration_is_rejected_and_original_survives() -> None:
    class _Impostor(BaseDiscovery):
        ats = ATSType.JAZZHR

        async def discover(self) -> list[Company]:
            return []

    with pytest.raises(DiscoveryError, match="Duplicate discoverer for 'jazzhr'"):
        DiscoveryRegistry.register(ATSType.JAZZHR)(_Impostor)

    assert DiscoveryRegistry.get(ATSType.JAZZHR).__name__ == "JazzHRSitemapDiscovery"


def test_reregistering_the_same_class_is_idempotent() -> None:
    """Re-importing a module must not look like a collision."""
    jazzhr = DiscoveryRegistry.get(ATSType.JAZZHR)
    assert DiscoveryRegistry.register(ATSType.JAZZHR)(jazzhr) is jazzhr
