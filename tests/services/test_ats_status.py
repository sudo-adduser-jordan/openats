from pathlib import Path
from unittest.mock import Mock

from services._base import CollectorRegistry
from services._models import ATSType
from services.ats_status import get_ats_status, log_ats_status


def test_status_partition(monkeypatch):
    monkeypatch.setattr(
        CollectorRegistry,
        "all",
        lambda: {ATSType.ASHBY: object, ATSType.LEVER: object, ATSType.EURES: object},
    )
    monkeypatch.setattr("services.ats_status.DISABLED_ATS", {ATSType.EURES, ATSType.CUSTOM})

    status = get_ats_status(["lever", "lever", "unknown", "custom"])

    assert status["enabled_ats"] == ["ashby"]
    assert status["disabled_ats"] == ["eures", "lever"]
    assert status["missing_ats"] == sorted(
        ats.value for ats in ATSType if ats not in {ATSType.ASHBY, ATSType.LEVER, ATSType.EURES}
    )
    flattened = [ats for group in status.values() for ats in group]
    assert len(flattened) == len(set(flattened)) == len(ATSType)


def test_current_registry():
    status = get_ats_status()
    assert status["missing_ats"] == ["custom"]
    assert status["disabled_ats"] == [
        "arbetsformedlingen",
        "bundesagentur",
        "eures",
        "join_com",
        "usajobs",
    ]
    assert "ashby" in status["enabled_ats"]
    assert all(group == sorted(group) for group in status.values())


def test_readme_table_matches_default_status():
    readme = (Path(__file__).resolve().parents[2] / "README.md").read_text(encoding="utf-8")
    table = readme.split("<!-- ats-status:start -->", 1)[1].split("<!-- ats-status:end -->", 1)[0]
    labels = {"enabled_ats": "Enabled", "disabled_ats": "Disabled", "missing_ats": "Missing"}
    rows = sorted((ats, labels[key]) for key, values in get_ats_status().items() for ats in values)
    expected = ["| ATS type | Status |", "| --- | --- |"]
    expected.extend(f"| `{ats}` | {status} |" for ats, status in rows)
    assert table.strip().splitlines() == expected


def test_log_status_includes_empty_lists(monkeypatch):
    monkeypatch.setattr(CollectorRegistry, "all", lambda: {})
    info = Mock()
    monkeypatch.setattr("services.ats_status.logger.info", info)

    log_ats_status()

    info.assert_called_once_with(
        operation="ats_status",
        missing_ats=sorted(ats.value for ats in ATSType),
        disabled_ats=[],
        enabled_ats=[],
    )
