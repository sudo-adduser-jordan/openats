import os
import threading
from queue import Queue
from typing import Any

from database.database import database
from utils.logger import logger
from utils.normalize import normalize_jobs


class Worker(threading.Thread):
    def __init__(self, q: Queue[Any], batch_size: int = 500) -> None:
        super().__init__()
        self.queue = q
        self.batch_size = batch_size
        self.buffer: list[Any] = []
        self.total_written = 0
        self._parquet_path = "data/parquet/jobs.parquet"
        self._parquet_writer: Any = None

    def run(self) -> None:
        logger.info(operation="pipeline_worker_start")
        self._clean_output_files()
        while True:
            item = self.queue.get()
            if item is None:
                self._flush()
                break
            self.buffer.extend(item)
            if len(self.buffer) >= self.batch_size:
                self._flush()
        self._close_parquet()
        logger.info(operation="pipeline_worker_stop", total_written=self.total_written)

    def _clean_output_files(self) -> None:
        if os.path.isfile(self._parquet_path):
            os.remove(self._parquet_path)

    def _flush(self) -> None:
        if not self.buffer:
            return
        try:
            rows = normalize_jobs(self.buffer)
            self._write_sqlite(rows)
            self._write_parquet(rows)
            self.total_written += len(rows)
            logger.info(operation="pipeline_flush", count=len(rows), total=self.total_written)
        except Exception as exc:
            logger.error(
                operation="pipeline_flush_error",
                error=str(exc),
                batch_size=len(self.buffer),
            )
        self.buffer.clear()

    def _write_sqlite(self, rows: list[dict[str, Any]]) -> None:
        with database.connect() as conn:
            database.insert_jobs(conn, rows)

    def _write_parquet(self, rows: list[dict[str, Any]]) -> None:
        if self._parquet_writer is None:
            from database.parquet import ParquetBufferWriter

            self._parquet_writer = ParquetBufferWriter(self._parquet_path)
        self._parquet_writer.write_rows(rows)

    def _close_parquet(self) -> None:
        if self._parquet_writer is not None:
            self._parquet_writer.close()
            self._parquet_writer = None
