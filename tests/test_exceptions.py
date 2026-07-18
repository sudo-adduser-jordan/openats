"""Verify the exception hierarchy is stable.

These are part of the public contract — third-party code catches them by
type, so renaming or reparenting must be a breaking change.
"""

import pytest

from exceptions import (
    AtsCollectorError,
    CollectorError,
    CompanyNotFoundError,
    ManifestError,
    StorageError,
)


def test_openats_error_is_subclass_of_exception() -> None:
    assert issubclass(AtsCollectorError, Exception)


@pytest.mark.parametrize(
    "exc",
    [ManifestError, StorageError, CollectorError],
)
def test_top_level_errors_inherit_from_openats_error(exc: type) -> None:
    assert issubclass(exc, AtsCollectorError)


def test_company_not_found_is_a_collector_error() -> None:
    assert issubclass(CompanyNotFoundError, CollectorError)
    assert issubclass(CompanyNotFoundError, AtsCollectorError)


def test_can_catch_all_with_openats_error() -> None:
    for exc in [ManifestError, StorageError, CollectorError, CompanyNotFoundError]:
        with pytest.raises(AtsCollectorError):
            raise exc("boom")


def test_exceptions_carry_message() -> None:
    err = CollectorError("greenhouse 503")
    assert "greenhouse" in str(err)
