"""Source survey reporting — the data behind ``openats discover verify``.

The survey is long-lived reference data rather than a live service, so the
interesting assertions are invariants: no duplicate entries, exactly one live
source, and no search or aggregator source claiming to work.
"""

from __future__ import annotations

from services._models import ATSType
from services.discover._sources import (
    SOURCES,
    SURVEY_DATE,
    SourceKind,
    SourceStatus,
    sources_by_status,
)
from services.discover.verify import (
    ProbeResult,
    format_report,
    probe_sources,
    unreachable_required,
)


def test_survey_entries_are_uniquely_labelled_and_addressed() -> None:
    urls = [source.url for source in SOURCES]
    labels = [source.label for source in SOURCES]
    assert len(urls) == len(set(urls))
    assert len(labels) == len(set(labels))
    assert all(source.url.startswith("https://") for source in SOURCES)
    assert all(source.notes for source in SOURCES)


def test_exactly_one_live_source_is_recorded() -> None:
    live = sources_by_status(SourceStatus.LIVE)
    assert len(live) == 1
    assert live[0].ats is ATSType.JAZZHR


def test_no_search_or_aggregator_source_claims_to_work() -> None:
    """The reason ``search.py`` and ``aggregator.py`` were deleted."""
    suspect = [
        source
        for source in SOURCES
        if source.kind in (SourceKind.SEARCH, SourceKind.AGGREGATOR)
    ]
    assert suspect, "the survey should still document why search was dropped"
    assert all(source.status is not SourceStatus.LIVE for source in suspect)


def test_sources_by_status_partitions_the_survey() -> None:
    counted = sum(len(sources_by_status(status)) for status in SourceStatus)
    assert counted == len(SOURCES)


def test_offline_probe_returns_every_source_without_touching_the_network() -> None:
    results = probe_sources(offline=True)
    assert len(results) == len(SOURCES)
    assert all(result.http_status is None for result in results)
    assert all(result.error is None for result in results)


def test_only_the_jazzhr_source_is_backed_by_a_registered_discoverer() -> None:
    registered = [result for result in probe_sources(offline=True) if result.registered]
    assert [result.source.ats for result in registered] == [ATSType.JAZZHR]


def test_offline_report_lists_every_source_and_the_survey_date() -> None:
    report = format_report(probe_sources(offline=True))
    assert report.splitlines()[0].startswith("STATUS")
    assert f"{len(SOURCES)} sources surveyed" in report
    assert SURVEY_DATE in report
    for source in SOURCES:
        assert source.label in report


def test_report_omits_urls_and_notes_unless_verbose() -> None:
    quiet = format_report(probe_sources(offline=True))
    loud = format_report(probe_sources(offline=True), verbose=True)
    assert SOURCES[0].url not in quiet
    assert SOURCES[0].notes not in quiet
    assert SOURCES[0].url in loud
    assert SOURCES[0].notes in loud


def test_unreachable_required_only_fails_probed_usable_sources() -> None:
    live = sources_by_status(SourceStatus.LIVE)[0]
    dead = sources_by_status(SourceStatus.DEAD)[0]
    auth = sources_by_status(SourceStatus.AUTH_REQUIRED)[0]

    # Never probed (an offline run) — nothing to report.
    assert unreachable_required([ProbeResult(live), ProbeResult(dead)]) == []
    # A usable source that was probed and never answered is a real problem.
    assert unreachable_required([ProbeResult(live, error="ConnectError")]) == [
        ProbeResult(live, error="ConnectError")
    ]
    # A dead source staying dead is the expected state.
    assert unreachable_required([ProbeResult(dead, error="ConnectError")]) == []
    # A usable source that answers is fine, whatever the status code.
    assert unreachable_required([ProbeResult(live, http_status=503)]) == []
    assert unreachable_required([ProbeResult(auth, http_status=401)]) == []


def test_offline_run_reports_no_unreachable_sources() -> None:
    assert unreachable_required(probe_sources(offline=True)) == []
