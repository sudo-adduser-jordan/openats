import contextlib
import os
import shutil

import dotenv

from cli import _run_collect_pipeline
from database.database import database
from services._models import DISABLED_ATS
from utils.logger import logger

dotenv.load_dotenv()


def main() -> None:
    nohup_out_removed = os.path.exists("nohup.out")
    logs_removed = os.path.isdir("logs")
    with contextlib.suppress(FileNotFoundError):
        os.remove("nohup.out")
    with contextlib.suppress(FileNotFoundError):
        shutil.rmtree("logs")
    logger.info(operation="cleanup", nohup_out_removed=nohup_out_removed, logs_removed=logs_removed)

    while True:
        with database.connect() as connection:
            companies_by_ats = database.read_companies_ats(connection)
            unknown_ats = database.read_companies_no_ats(connection)

        companies_by_ats = {k: v for k, v in companies_by_ats.items() if k not in DISABLED_ATS}

        total_companies = sum(len(v) for v in companies_by_ats.values())
        logger.info(
            operation="read_companies", total=total_companies, unknown_ats_skipped=unknown_ats or None
        )

        outcome, written, duration = _run_collect_pipeline(companies_by_ats)
        logger.info(
            operation="collect_pipeline",
            outcome=outcome,
            pipeline="openats",
            companies_total=total_companies,
            jobs_persisted=written,
            duration_ms=duration,
            unknown_ats_skipped=unknown_ats or None,
        )

        if outcome == "cancelled":
            logger.info(operation="pipeline_shutdown", outcome=outcome)
            break


if __name__ == "__main__":
    main()
