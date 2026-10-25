"""The default run mode fetches one company at a time; ``--concurrent`` opts
back into the thread-pool fan-out."""

import threading
import time
from contextlib import nullcontext
from queue import Empty, Queue
from unittest.mock import Mock

import pytest

import cli
import producer
from services._models import ATSType


@pytest.mark.parametrize(
    ("arguments", "expected"),
    [
        ([], False),
        (["--concurrent"], True),
        (["--concurrent", "collect", "ats", "ashby"], True),
        (["collect", "ats", "ashby"], False),
        (["collect", "ats", "ashby", "--concurrent"], True),
        (["collect", "company", "openai", "--concurrent"], True),
        (["collect", "watchlist", "--concurrent"], True),
        (["collect", "--concurrent", "--skip", "meta"], True),
        (["collect", "--skip", "meta"], False),
    ],
)
def test_concurrent_flag_accepted_in_every_position(arguments, expected):
    """Global and per-subcommand positions must not clobber each other."""
    assert cli._build_parser().parse_args(arguments).concurrent is expected


@pytest.mark.parametrize(
    ("arguments", "expected"),
    [
        ([], False),
        (["--concurrent"], True),
        (["collect", "--concurrent"], True),
        (["collect"], False),
    ],
)
def test_continuous_run_forwards_concurrent_flag(monkeypatch, arguments, expected):
    """The bare run and ``collect`` hand their flag to ``app.main``."""
    import app

    captured = {}

    def fake_main(concurrent=False):
        captured["concurrent"] = concurrent

    monkeypatch.setattr(app, "main", fake_main)
    monkeypatch.setattr("sys.argv", ["openats", *arguments])

    cli.main()

    assert captured["concurrent"] is expected


def test_collect_pipeline_forwards_concurrent_flag(monkeypatch):
    captured = {}

    def fake_run_producers(ingest_queue, companies_by_ats, shutdown_event, concurrent=False):
        captured["concurrent"] = concurrent
        return 0, 0, 0

    class FakeWorker:
        total_written = 0

        def __init__(self, q, batch_size=500):
            pass

        def start(self):
            pass

        def join(self):
            pass

    monkeypatch.setattr(cli, "run_producers", fake_run_producers)
    monkeypatch.setattr(cli, "Worker", FakeWorker)
    monkeypatch.setattr(cli, "setup_signal_handlers", lambda *args, **kwargs: None)
    monkeypatch.setattr(cli.database, "connect", lambda: nullcontext(Mock()))
    monkeypatch.setattr(cli.database, "dump_jobs_recent", lambda connection: None)

    cli._run_collect_pipeline({ATSType.ASHBY: []}, concurrent=True)
    assert captured["concurrent"] is True

    cli._run_collect_pipeline({ATSType.ASHBY: []})
    assert captured["concurrent"] is False


def _tracking_fetch(sleep_s: float):
    """Return a ``_fetch_jobs`` stand-in that records peak concurrency."""
    active = 0
    peak = 0
    lock = threading.Lock()

    def fake_fetch(ats_type, slug, name, url=None):
        nonlocal active, peak
        with lock:
            active += 1
            peak = max(peak, active)
        time.sleep(sleep_s)
        with lock:
            active -= 1
        return [{"slug": slug}]

    return fake_fetch, lambda: peak


def _drain(queue) -> int:
    count = 0
    while True:
        try:
            queue.get_nowait()
            count += 1
        except Empty:
            return count


def test_default_mode_fetches_one_company_at_a_time(monkeypatch):
    fake_fetch, peak = _tracking_fetch(sleep_s=0.02)
    monkeypatch.setattr(producer, "_fetch_jobs", fake_fetch)

    queue: Queue = Queue(maxsize=100)
    companies = {ATSType.ASHBY: [{"slug": f"c{i}", "name": f"C{i}"} for i in range(6)]}

    total_companies, total_jobs, failures = producer.run_producers(
        queue, companies, threading.Event()
    )

    assert (total_companies, total_jobs, failures) == (6, 6, 0)
    assert peak() == 1, "sequential mode must never overlap fetches"
    assert _drain(queue) == 6, "every company's jobs must reach the ingest queue"


def test_concurrent_mode_overlaps_fetches(monkeypatch):
    fake_fetch, peak = _tracking_fetch(sleep_s=0.05)
    monkeypatch.setattr(producer, "_fetch_jobs", fake_fetch)
    monkeypatch.setattr(producer, "CONCURRENCY", 4)

    queue: Queue = Queue(maxsize=100)
    companies = {ATSType.ASHBY: [{"slug": f"c{i}", "name": f"C{i}"} for i in range(8)]}

    total_companies, total_jobs, failures = producer.run_producers(
        queue, companies, threading.Event(), concurrent=True
    )

    assert (total_companies, total_jobs, failures) == (8, 8, 0)
    assert peak() >= 2, "--concurrent must fan fetches out over the pool"
    assert _drain(queue) == 8


def test_failures_are_counted_in_both_modes(monkeypatch):
    def failing_fetch(ats_type, slug, name, url=None):
        raise RuntimeError("boom")

    monkeypatch.setattr(producer, "_fetch_jobs", failing_fetch)
    queue: Queue = Queue(maxsize=100)
    companies = {ATSType.ASHBY: [{"slug": "c0", "name": "C0"}]}

    for concurrent in (False, True):
        total_companies, total_jobs, failures = producer.run_producers(
            queue, companies, threading.Event(), concurrent=concurrent
        )
        assert (total_companies, total_jobs, failures) == (1, 0, 1)


def test_progress_logs_every_thousand_in_sequential_mode(monkeypatch):
    """Guards the ``collect_progress`` log, which only fires past 1000 fetches."""
    monkeypatch.setattr(
        producer, "_fetch_jobs", lambda ats_type, slug, name, url=None: [{"slug": slug}]
    )
    info = Mock()
    monkeypatch.setattr(producer.logger, "info", info)

    queue: Queue = Queue(maxsize=100_000)
    companies = {ATSType.ASHBY: [{"slug": f"c{i}", "name": f"C{i}"} for i in range(1000)]}

    producer.run_producers(queue, companies, threading.Event())

    progress = [
        call.kwargs
        for call in info.call_args_list
        if call.kwargs.get("operation") == "collect_progress"
    ]
    assert progress == [
        {
            "operation": "collect_progress",
            "processed": 1000,
            "total": 1000,
            "jobs_collected": 1000,
            "failures": 0,
        }
    ]
