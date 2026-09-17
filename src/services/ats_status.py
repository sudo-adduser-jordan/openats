"""Configuration-level ATS availability, independent of company data or credentials."""

from collections.abc import Iterable
from typing import TypedDict

from services._base import CollectorRegistry
from services._models import DISABLED_ATS, ATSType
from utils.logger import logger


class ATSStatus(TypedDict):
    missing_ats: list[str]
    disabled_ats: list[str]
    enabled_ats: list[str]


def get_ats_status(skipped_ats: Iterable[str] = ()) -> ATSStatus:
    """Partition known ATS types into sorted, disjoint configuration lists.

    ATSType defines known types; CollectorRegistry defines usable registrations
    (services.__init__ imports collectors before this module is loaded). Missing
    means no registered collector, including CUSTOM or an unregistered implementation,
    and takes precedence over exclusions. Disabled means registered but excluded
    by DISABLED_ATS or an explicit ATS skip for this invocation. Unknown skip names
    are ignored. Enabled does not imply credentials, network health, or companies
    are available, nor that an ATS was selected by a company/ATS/watchlist filter.
    """
    known = {ats.value for ats in ATSType}
    registered = {ats.value for ats in CollectorRegistry.all()} & known
    excluded = {ats.value for ats in DISABLED_ATS} | set(skipped_ats)
    return {
        "missing_ats": sorted(known - registered),
        "disabled_ats": sorted(registered & excluded),
        "enabled_ats": sorted(registered - excluded),
    }


def log_ats_status(skipped_ats: Iterable[str] = ()) -> None:
    """Emit one startup event containing all three lists, including empty ones."""
    logger.info(operation="ats_status", **get_ats_status(skipped_ats))
