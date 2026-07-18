import contextlib
import signal
import threading
from queue import Queue
from typing import Any

from utils.logger import logger


def setup_signal_handlers(shutdown_event: threading.Event, ingest_queue: Queue[Any]) -> None:
    def _shutdown(signum: int, frame: object) -> None:
        logger.info(operation="signal_received", signal=signum)
        shutdown_event.set()
        with contextlib.suppress(Exception):
            ingest_queue.put_nowait(None)

    signal.signal(signal.SIGINT, _shutdown)
    signal.signal(signal.SIGTERM, _shutdown)
