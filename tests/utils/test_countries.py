"""Tests for country ISO and region inference."""

from __future__ import annotations

import pytest

from utils.countries import (
    _COUNTRY_NAME_TO_ISO,
    _COUNTRY_TO_LANGUAGE,
    _COUNTRY_TO_REGION,
    _LOCATION_ISO_LOOKUP,
    country_to_region,
    infer_country_iso,
    infer_language,
)

# --- infer_country_iso -------------------------------------------------------


@pytest.mark.parametrize(
    ("location", "expected"),
    [
        ("San Francisco, United States", "US"),
        ("Paris, France", "FR"),
        ("Berlin, Germany", "DE"),
        ("Tokyo, Japan", "JP"),
        ("Sydney, Australia", "AU"),
        ("São Paulo, Brazil", "BR"),
        ("Mumbai, India", "IN"),
        ("Lagos, Nigeria", "NG"),
        ("Cape Town, South Africa", "ZA"),
        ("Seoul, South Korea", "KR"),
    ],
)
def test_infer_from_country_name(location: str, expected: str) -> None:
    assert infer_country_iso(location) == expected


@pytest.mark.parametrize(
    ("location", "expected"),
    [
        ("Austin, Texas", "US"),
        ("San Francisco, California", "US"),
        ("New York City, New York", "US"),
        ("Seattle, Washington", "US"),
        ("Boston, Massachusetts", "US"),
        ("Chicago, Illinois", "US"),
        ("Miami, Florida", "US"),
        ("Denver, Colorado", "US"),
        ("Portland, Oregon", "US"),
    ],
)
def test_infer_from_us_state(location: str, expected: str) -> None:
    assert infer_country_iso(location) == expected


@pytest.mark.parametrize(
    ("location", "expected"),
    [
        ("Toronto, Ontario", "CA"),
        ("Vancouver, British Columbia", "CA"),
        ("Montreal, Quebec", "CA"),
        ("Calgary, Alberta", "CA"),
    ],
)
def test_infer_from_ca_province(location: str, expected: str) -> None:
    assert infer_country_iso(location) == expected


@pytest.mark.parametrize(
    ("location", "expected"),
    [
        ("DE", "DE"),
        ("US", "US"),
        ("FR", "FR"),
        ("GB", "GB"),
        ("JP", "JP"),
    ],
)
def test_infer_from_iso_code(location: str, expected: str) -> None:
    assert infer_country_iso(location) == expected


def test_infer_country_iso_none() -> None:
    assert infer_country_iso(None) is None


@pytest.mark.parametrize("location", ["", "   "])
def test_infer_country_iso_empty(location: str) -> None:
    assert infer_country_iso(location) is None


def test_infer_country_iso_unknown() -> None:
    assert infer_country_iso("Somewhere, Nowhere") is None


def test_infer_country_iso_with_deutschland() -> None:
    """Non-English country name should also resolve."""
    assert infer_country_iso("München, Deutschland") == "DE"


@pytest.mark.parametrize(
    ("location", "expected"),
    [
        ("Remote — US", "US"),
        ("UK — Remote", "GB"),
        ("Remote - Anywhere", None),
    ],
)
def test_infer_with_remote_prefix(location: str, expected: str | None) -> None:
    assert infer_country_iso(location) == expected


# --- country_to_region -------------------------------------------------------


@pytest.mark.parametrize(
    ("iso", "expected"),
    [
        ("US", "North America"),
        ("CA", "North America"),
        ("MX", "North America"),
        ("DE", "Europe"),
        ("FR", "Europe"),
        ("GB", "Europe"),
        ("BR", "South America"),
        ("AR", "South America"),
        ("JP", "Asia"),
        ("CN", "Asia"),
        ("IN", "Asia"),
        ("AU", "Oceania"),
        ("NZ", "Oceania"),
        ("ZA", "Africa"),
        ("NG", "Africa"),
        ("AQ", "Antarctica"),
    ],
)
def test_country_to_region_known(iso: str, expected: str) -> None:
    assert country_to_region(iso) == expected


def test_country_to_region_none() -> None:
    assert country_to_region(None) is None


def test_country_to_region_unknown_code() -> None:
    assert country_to_region("ZZ") is None


def test_country_to_region_lowercase() -> None:
    assert country_to_region("us") == "North America"


# --- Mapping integrity -------------------------------------------------------


def test_all_country_names_have_region() -> None:
    """Every country name in the lookup table maps to a valid ISO code
    that exists in the region table (except possibly codes like ``CS``
    that are not in our region table — catch those)."""
    for name, iso in _COUNTRY_NAME_TO_ISO.items():
        assert iso in _COUNTRY_TO_REGION, f"'{name}' -> {iso} missing from _COUNTRY_TO_REGION"


def test_all_us_states_have_region() -> None:
    """All US state entries must map to a valid region entry."""
    from utils.countries import _US_STATES

    for state, iso in _US_STATES.items():
        assert iso in _COUNTRY_TO_REGION, f"'{state}' -> {iso} missing from _COUNTRY_TO_REGION"


def test_all_ca_provinces_have_region() -> None:
    from utils.countries import _CA_PROVINCES

    for province, iso in _CA_PROVINCES.items():
        assert iso in _COUNTRY_TO_REGION, f"'{province}' -> {iso} missing from _COUNTRY_TO_REGION"


def test_location_lookup_integrity() -> None:
    """Every entry in the combined lookup table must have an ISO in the
    region table."""
    for key, iso in _LOCATION_ISO_LOOKUP.items():
        assert iso in _COUNTRY_TO_REGION, f"'{key}' -> {iso} invalid"


def test_region_values() -> None:
    """Continent values must be the canonical set."""
    valid = {"Africa", "Antarctica", "Asia", "Europe", "North America", "Oceania", "South America"}
    for iso, region in _COUNTRY_TO_REGION.items():
        assert region in valid, f"{iso} -> {region!r} not a valid continent"


# --- infer_language -----------------------------------------------------------


@pytest.mark.parametrize(
    ("country_iso", "expected"),
    [
        ("US", "en"),
        ("GB", "en"),
        ("DE", "de"),
        ("FR", "fr"),
        ("ES", "es"),
        ("IT", "it"),
        ("PT", "pt"),
        ("NL", "nl"),
        ("SE", "sv"),
        ("DK", "da"),
        ("NO", "nb"),
        ("FI", "fi"),
        ("PL", "pl"),
        ("CZ", "cs"),
        ("JP", "ja"),
        ("KR", "ko"),
        ("CN", "zh"),
        ("RU", "ru"),
        ("BR", "pt"),
        ("AR", "es"),
        ("MX", "es"),
        ("IN", "en"),
        ("SG", "en"),
        ("ZA", "en"),
        ("NG", "en"),
        ("AU", "en"),
        ("CA", "en"),
        ("CH", "de"),
        ("BE", "nl"),
        ("AT", "de"),
    ],
)
def test_infer_language_known(country_iso: str, expected: str) -> None:
    assert infer_language(country_iso) == expected


def test_infer_language_none() -> None:
    assert infer_language(None) is None


def test_infer_language_unknown_code() -> None:
    assert infer_language("ZZ") is None


def test_infer_language_lowercase() -> None:
    assert infer_language("de") == "de"


def test_all_country_isos_have_language() -> None:
    """Every ISO code in the country-to-language map must correspond to
    an entry in the region table (i.e. all codes are valid ISO 3166-1
    alpha-2 codes that we recognise)."""
    for iso in _COUNTRY_TO_LANGUAGE:
        assert iso in _COUNTRY_TO_REGION, (
            f"{iso} in _COUNTRY_TO_LANGUAGE but missing from _COUNTRY_TO_REGION"
        )


def test_all_region_isos_have_language() -> None:
    """Every ISO code in the region table should have a language mapping."""
    for iso in _COUNTRY_TO_REGION:
        if iso == "TF":
            continue  # French Southern Territories — no population, skip
        assert iso in _COUNTRY_TO_LANGUAGE, f"{iso} has a region mapping but no language mapping"
