import concurrent.futures
import random
import threading
import time

from services._base import CollectorRegistry
from utils.logger import logger


class TokenBucket:
    """Thread-safe token bucket rate limiter per ATS type."""

    # def __init__(self, rate: float = 10.0, burst: int | None = None) -> None:
    # def __init__(self, rate: float = 1.0, burst: int | None = None) -> None:
    def __init__(self, rate: float = 2.0, burst: int | None = None) -> None:
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


def run_producers(ingest_queue, companies_by_ats, shutdown_event):
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

    # with concurrent.futures.ThreadPoolExecutor(max_workers=64) as pool:
    # with concurrent.futures.ThreadPoolExecutor(max_workers=4) as pool:
    with concurrent.futures.ThreadPoolExecutor(max_workers=16) as pool:
        future_map = {}
        for ats_type, c in entries:
            future = pool.submit(_fetch_jobs, ats_type, c["slug"], c["name"], c.get("url"))
            future_map[future] = (ats_type, c["slug"], c["name"], c.get("url", ""))
        for processed, future in enumerate(concurrent.futures.as_completed(future_map), start=1):
            if shutdown_event.is_set():
                break

            ats_type, slug, name, url = future_map[future]
            try:
                jobs = future.result()
                if shutdown_event.is_set():
                    break
                if jobs:
                    ingest_queue.put(jobs)
                    total_jobs += len(jobs)

            except Exception as exc:
                failure_count += 1
                logger.error(
                    operation="collect_failure",
                    ats=ats_type.value,
                    slug=slug,
                    name=name,
                    url=url,
                    error=str(exc),
                )
            finally:
                del future_map[future]

            if processed % 1000 == 0:
                logger.info(
                    operation="collect_progress",
                    processed=processed,
                    total=total_companies,
                    jobs_collected=total_jobs,
                    failures=failure_count,
                )

    return total_companies, total_jobs, failure_count
