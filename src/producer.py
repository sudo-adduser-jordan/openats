import random
import threading
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from queue import Full

from config import CONCURRENCY, REQUEST_RATE
from services._base import CollectorRegistry
from utils.logger import logger


class TokenBucket:
    """Thread-safe token bucket rate limiter per ATS type."""

    def __init__(self, rate: int = REQUEST_RATE, burst: int | None = None) -> None:
        self._rate = rate
        self._burst = burst or max(1, int(rate))
        self._tokens = float(self._burst)
        self._last_refill = time.monotonic()
        self._lock = threading.Lock()

    def acquire(self, tokens: float = 1.0) -> float:
        with self._lock:
            now = time.monotonic()
            elapsed = now - self._last_refill
            self._tokens = min(float(self._burst), self._tokens + elapsed * self._rate)
            self._last_refill = now

            if self._tokens >= tokens:
                self._tokens -= tokens
                return 0.0

            deficit = tokens - self._tokens
            sleep_time = deficit / self._rate
            self._tokens = 0.0
            self._last_refill = now + sleep_time

        if sleep_time > 0:
            time.sleep(sleep_time)
        return sleep_time


_rate_limiters: dict[str, TokenBucket] = {}
_rate_lock = threading.Lock()


def _get_limiter(ats: str) -> TokenBucket:
    with _rate_lock:
        if ats not in _rate_limiters:
            _rate_limiters[ats] = TokenBucket()
        return _rate_limiters[ats]


def _fetch_jobs(ats_type, slug, name, url=None):
    _get_limiter(ats_type.value).acquire()
    jobs = CollectorRegistry.get(ats_type)(slug, url=url).fetch()
    if jobs:
        logger.info(
            operation="fetch_result",
            ats=ats_type.value,
            slug=slug,
            name=name,
            url=url or "",
            jobs=len(jobs),
        )
    return jobs


def _fetch_results(entries, concurrent: bool, shutdown_event):
    """Yield ``(ats_type, slug, name, url, outcome)`` for every company.

    ``outcome`` is either the fetched job list or the exception raised while
    fetching — the caller does the accounting so both modes behave alike.

    With ``concurrent`` the companies are fanned out over a thread pool and
    yielded in completion order; without it they are fetched one at a time in
    the calling thread, which is the default ("one process") run mode.
    """
    if concurrent:
        with ThreadPoolExecutor(max_workers=CONCURRENCY) as pool:
            future_map = {}
            for ats_type, c in entries:
                future = pool.submit(_fetch_jobs, ats_type, c["slug"], c["name"], c.get("url"))
                future_map[future] = (ats_type, c["slug"], c["name"], c.get("url", ""))
            for future in as_completed(future_map):
                if shutdown_event.is_set():
                    return

                ats_type, slug, name, url = future_map.pop(future)
                try:
                    yield ats_type, slug, name, url, future.result()
                except Exception as exc:
                    yield ats_type, slug, name, url, exc
        return

    for ats_type, c in entries:
        if shutdown_event.is_set():
            return

        slug, name, url = c["slug"], c["name"], c.get("url")
        try:
            yield ats_type, slug, name, url, _fetch_jobs(ats_type, slug, name, url)
        except Exception as exc:
            yield ats_type, slug, name, url, exc


def run_producers(ingest_queue, companies_by_ats, shutdown_event, concurrent: bool = False):
    total_companies = sum(len(v) for v in companies_by_ats.values())
    total_jobs = 0
    failure_count = 0

    if total_companies == 0:
        return 0, 0, 0

    ats_items = list(companies_by_ats.items())
    random.shuffle(ats_items)

    for _, companies in ats_items:
        random.shuffle(companies)

    entries = []
    max_len = max(len(c) for _, c in ats_items)
    for i in range(max_len):
        for ats_type, companies in ats_items:
            if i < len(companies):
                entries.append((ats_type, companies[i]))

    results = enumerate(_fetch_results(entries, concurrent, shutdown_event), start=1)
    for count, (ats_type, slug, name, url, outcome) in results:
        if shutdown_event.is_set():
            break

        if isinstance(outcome, Exception):
            failure_count += 1
            logger.error(
                operation="collect_failure",
                ats=ats_type.value,
                slug=slug,
                name=name,
                url=url or "",
                error=str(outcome),
            )
        elif outcome:
            jobs = outcome
            while True:
                try:
                    ingest_queue.put_nowait(jobs)
                    break
                except Full:
                    if shutdown_event.is_set():
                        break
                    time.sleep(0.1)
            total_jobs += len(jobs)

        if count % 1000 == 0:
            logger.info(
                operation="collect_progress",
                processed=count,
                total=total_companies,
                jobs_collected=total_jobs,
                failures=failure_count,
            )

    return total_companies, total_jobs, failure_count
