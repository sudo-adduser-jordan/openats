import os
from typing import Any

import pyarrow as pa
import pyarrow.parquet as pq


class ParquetBufferWriter:
    def __init__(self, path: str) -> None:
        self.path = path
        self._writer: pq.ParquetWriter | None = None
        self._schema: pa.Schema | None = None

    def write_rows(self, rows: list[dict[str, Any]]) -> None:
        if not rows:
            return
        table = pa.Table.from_pylist(rows)
        if self._writer is None:
            os.makedirs(os.path.dirname(self.path), exist_ok=True)
            # Promote null-typed columns to string to avoid cast errors
            # when later batches contain values in those columns
            fields = []
            for field in table.schema:
                if pa.types.is_null(field.type):
                    fields.append(pa.field(field.name, pa.string()))
                else:
                    fields.append(field)
            self._schema = pa.schema(fields)
            table = table.cast(self._schema)
            self._writer = pq.ParquetWriter(self.path, self._schema)  # type: ignore[no-untyped-call]
        else:
            table = table.cast(self._schema)
        self._writer.write_table(table)  # type: ignore[no-untyped-call]

    def close(self) -> None:
        if self._writer is not None:
            self._writer.close()  # type: ignore[no-untyped-call]
            self._writer = None

    def __enter__(self):
        return self

    def __exit__(self, *args):
        self.close()
