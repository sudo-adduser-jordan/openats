import signal
import threading
from queue import Empty, Full, Queue
from typing import Any

from utils.logger import logger


def _drain_and_signal(ingest_queue: Queue[Any], shutdown_event: threading.Event) -> None:
    """Deliver the sentinel to the worker even when the queue is full."""
    for _ in range(10):
        try:
            ingest_queue.put_nowait(None)
            return
        except Full:
            try:
                ingest_queue.get_nowait()
            except Empty:
                return
    shutdown_event.set()


def setup_signal_handlers(shutdown_event: threading.Event, ingest_queue: Queue[Any]) -> None:
    def _shutdown(signum: int, frame: object) -> None:
        logger.info(operation="signal_received", signal=signum)
        _drain_and_signal(ingest_queue, shutdown_event)

    signal.signal(signal.SIGINT, _shutdown)
    signal.signal(signal.SIGTERM, _shutdown)
