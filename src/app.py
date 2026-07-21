import dotenv

from cli import _run_collect_pipeline
from database.database import database
from services._models import DISABLED_ATS
from utils.logger import logger

dotenv.load_dotenv()


def main() -> None:
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


if __name__ == "__main__":
    main()
