from __future__ import annotations

import os
import re
import sqlite3
from contextlib import contextmanager
from datetime import UTC, datetime, timedelta
from typing import ClassVar

from services._models import ATSType
from utils.logger import logger

_STANDARD_TABLES = frozenset({"companies", "ats", "jobs", "watchlists"})

JOBS_TABLE = "jobs"

CREATE_JOBS_TABLE = """
CREATE TABLE IF NOT EXISTS jobs (
    global_id TEXT PRIMARY KEY,
    url TEXT NOT NULL,
    title TEXT NOT NULL,
    company TEXT NOT NULL,
    ats_type TEXT NOT NULL,
    ats_id TEXT,
    location TEXT,
    country_iso TEXT,
    region TEXT,
    lat REAL,
    lon REAL,
    is_remote INTEGER,
    salary_currency TEXT,
    salary_period TEXT,
    salary_summary TEXT,
    salary_min REAL,
    salary_max REAL,
    experience INTEGER,
    employment_type TEXT,
    department TEXT,
    team TEXT,
    requisition_id TEXT,
    apply_url TEXT,
    commitment TEXT,
    description TEXT,
    posted_at TEXT,
    fetched_at TEXT,
    language TEXT,
    raw TEXT
)
"""

CREATE_COMPANIES_TABLE = (
    "CREATE TABLE IF NOT EXISTS companies (ats TEXT, name TEXT, slug TEXT, url TEXT, "
    "active INTEGER DEFAULT 1, last_collected_at TEXT, last_jobs_count INTEGER, last_url_check TEXT)"
)
CREATE_INDEX_COMPANIES_ATS = "CREATE INDEX IF NOT EXISTS idx_companies_ats ON companies(ats)"
CREATE_INDEX_COMPANIES_SLUG = "CREATE INDEX IF NOT EXISTS idx_companies_slug ON companies(slug)"
CREATE_INDEX_COMPANIES_NAME = "CREATE INDEX IF NOT EXISTS idx_companies_name ON companies(name)"
CREATE_INDEX_JOBS_COMPANY = 'CREATE INDEX IF NOT EXISTS idx_jobs_company ON "jobs"(company)'
CREATE_INDEX_JOBS_ATS_TYPE = 'CREATE INDEX IF NOT EXISTS idx_jobs_ats_type ON "jobs"(ats_type)'
CREATE_INDEX_JOBS_POSTED_AT = 'CREATE INDEX IF NOT EXISTS idx_jobs_posted_at ON "jobs"(posted_at)'
CREATE_INDEX_JOBS_RECENT_POSTED_AT = (
    'CREATE INDEX IF NOT EXISTS idx_jobs_recent_posted_at ON "jobs_recent"(posted_at)'
)
CREATE_INDEX_WATCHLISTS_WATCHLIST = (
    "CREATE INDEX IF NOT EXISTS idx_watchlists_watchlist ON watchlists(watchlist)"
)
CREATE_INDEX_JOBS_COUNTRY_ISO = (
    'CREATE INDEX IF NOT EXISTS idx_jobs_country_iso ON "jobs"(country_iso)'
)
CREATE_INDEX_JOBS_REGION = 'CREATE INDEX IF NOT EXISTS idx_jobs_region ON "jobs"(region)'
CREATE_INDEX_JOBS_LANGUAGE = 'CREATE INDEX IF NOT EXISTS idx_jobs_language ON "jobs"(language)'
CREATE_INDEX_JOBS_ATS_TYPE_POSTED_AT = (
    'CREATE INDEX IF NOT EXISTS idx_jobs_ats_type_posted_at ON "jobs"(ats_type, posted_at)'
)
CREATE_INDEX_JOBS_COMPANY_POSTED_AT = (
    'CREATE INDEX IF NOT EXISTS idx_jobs_company_posted_at ON "jobs"(company, posted_at)'
)
CREATE_INDEX_COMPANIES_URL = "CREATE INDEX IF NOT EXISTS idx_companies_url ON companies(url)"

NOT_SENIOR_MANAGER = """
    AND "title" NOT LIKE '%senior%'
    AND "title" NOT LIKE '%director%'
    AND "title" NOT LIKE '%sr.%'
    AND "title" NOT LIKE '%sr %'
    AND "title" NOT LIKE '%manager%'
    AND "title" NOT LIKE '%principal%'
    AND "title" NOT LIKE '%lead%'
    AND "title" NOT LIKE '%vp of%'
"""

CREATE_VIEW_JUNIOR_US_SOFTWARE = f"""
CREATE VIEW IF NOT EXISTS view_junior_us_software AS
SELECT * FROM "jobs"
WHERE "title" LIKE '%software%'
AND "title" LIKE '%junior%'{NOT_SENIOR_MANAGER}AND "country_iso" LIKE '%US%'
ORDER BY "is_remote"
"""

CREATE_VIEW_US_SOFTWARE = f"""
CREATE VIEW IF NOT EXISTS view_us_software AS
SELECT * FROM "jobs"
WHERE "title" LIKE '%software%'{NOT_SENIOR_MANAGER}AND "country_iso" LIKE '%US%'
ORDER BY "is_remote"
"""

CREATE_VIEW_US_DEVELOPER = f"""
CREATE VIEW IF NOT EXISTS view_us_developer AS
SELECT * FROM "jobs"
WHERE "title" LIKE '%developer%'{NOT_SENIOR_MANAGER}AND "country_iso" LIKE '%US%'
ORDER BY "is_remote"
"""

CREATE_VIEW_JUNIOR_US_DEVELOPER = f"""
CREATE VIEW IF NOT EXISTS view_junior_us_developer AS
SELECT * FROM "jobs"
WHERE "title" LIKE '%developer%'
AND "title" LIKE '%junior%'{NOT_SENIOR_MANAGER}AND "country_iso" LIKE '%US%'
ORDER BY "is_remote"
"""

CREATE_VIEW_US_FRONTEND = f"""
CREATE VIEW IF NOT EXISTS view_us_frontend AS
SELECT * FROM "jobs"
WHERE "title" LIKE '%frontend%'{NOT_SENIOR_MANAGER}AND "country_iso" LIKE '%US%'
ORDER BY "is_remote"
"""

CREATE_VIEW_JUNIOR_US_SOFTWARE_24H = f"""
CREATE VIEW IF NOT EXISTS view_junior_us_software_24h AS
SELECT * FROM "jobs_recent"
WHERE "title" LIKE '%software%'
AND "title" LIKE '%junior%'{NOT_SENIOR_MANAGER}AND "country_iso" LIKE '%US%'
ORDER BY "is_remote"
"""

CREATE_VIEW_US_SOFTWARE_24H = f"""
CREATE VIEW IF NOT EXISTS view_us_software_24h AS
SELECT * FROM "jobs_recent"
WHERE "title" LIKE '%software%'{NOT_SENIOR_MANAGER}AND "country_iso" LIKE '%US%'
ORDER BY "is_remote"
"""

CREATE_VIEW_US_DEVELOPER_24H = f"""
CREATE VIEW IF NOT EXISTS view_us_developer_24h AS
SELECT * FROM "jobs_recent"
WHERE "title" LIKE '%developer%'{NOT_SENIOR_MANAGER}AND "country_iso" LIKE '%US%'
ORDER BY "is_remote"
"""

CREATE_VIEW_JUNIOR_US_DEVELOPER_24H = f"""
CREATE VIEW IF NOT EXISTS view_junior_us_developer_24h AS
SELECT * FROM "jobs_recent"
WHERE "title" LIKE '%developer%'
AND "title" LIKE '%junior%'{NOT_SENIOR_MANAGER}AND "country_iso" LIKE '%US%'
ORDER BY "is_remote"
"""

CREATE_VIEW_US_FRONTEND_24H = f"""
CREATE VIEW IF NOT EXISTS view_us_frontend_24h AS
SELECT * FROM "jobs_recent"
WHERE "title" LIKE '%frontend%'{NOT_SENIOR_MANAGER}AND "country_iso" LIKE '%US%'
ORDER BY "is_remote"
"""

SELECT_COMPANIES_ATS = "SELECT ats, name, slug, url FROM companies"
SELECT_ALL_COMPANIES = "SELECT * FROM companies"
SELECT_ALL_ATS = "SELECT * FROM ats"

PRAGMA_JOURNAL_WAL = "PRAGMA journal_mode=WAL"
PRAGMA_SYNCHRONOUS_NORMAL = "PRAGMA synchronous=NORMAL"
PRAGMA_CACHE_SIZE = "PRAGMA cache_size = -64000"
PRAGMA_BUSY_TIMEOUT = "PRAGMA busy_timeout = 5000"
PRAGMA_TEMP_STORE = "PRAGMA temp_store = MEMORY"
PRAGMA_MMAP_SIZE = "PRAGMA mmap_size = 268435456"
INSERT_COMPANY = "INSERT OR IGNORE INTO companies (ats, name, slug, url, active, last_collected_at, last_jobs_count, last_url_check) VALUES (?, ?, ?, ?, 1, NULL, NULL, NULL)"

DROP_ATS_TABLE = "DROP TABLE IF EXISTS ats"
CREATE_ATS_TABLE = "CREATE TABLE ats (ats TEXT, name TEXT, slug TEXT)"
DROP_JOBS_TABLE = "DROP TABLE IF EXISTS jobs"
DELETE_JOBS = "DELETE FROM jobs"
CREATE_UNIQUE_INDEX_COMPANIES = (
    "CREATE UNIQUE INDEX IF NOT EXISTS idx_companies_unique ON companies(ats, name, slug)"
)
CREATE_UNIQUE_INDEX_ATS = "CREATE UNIQUE INDEX IF NOT EXISTS idx_ats_unique ON ats(ats)"
SELECT_COMPANIES_COUNT = "SELECT COUNT(*) FROM companies"
SELECT_NON_STANDARD_TABLES = (
    "SELECT name FROM sqlite_master WHERE type='table' AND name NOT IN "
    "('companies', 'jobs', 'ats', 'watchlists', 'jobs_recent', 'sqlite_sequence')"
)

DROP_WATCHLISTS_TABLE = "DROP TABLE IF EXISTS watchlists"
CREATE_WATCHLISTS_TABLE = """
CREATE TABLE IF NOT EXISTS watchlists (
    ats TEXT NOT NULL,
    company_name TEXT NOT NULL,
    company_slug TEXT NOT NULL,
    watchlist TEXT NOT NULL DEFAULT '',
    created_at TEXT NOT NULL DEFAULT (datetime('now')),
    UNIQUE(ats, company_slug)
)
"""
INSERT_WATCHLIST = "INSERT OR IGNORE INTO watchlists (ats, company_name, company_slug, watchlist) VALUES (?, ?, ?, ?)"
DELETE_WATCHLIST = "DELETE FROM watchlists WHERE ats = ? AND company_slug = ?"
CLEAR_WATCHLISTS = "DELETE FROM watchlists"
SELECT_WATCHLISTS = "SELECT * FROM watchlists ORDER BY created_at DESC"
SELECT_WATCHLIST_CHECK = "SELECT COUNT(*) FROM watchlists WHERE ats = ? AND company_slug = ?"
SELECT_COMPANIES_BY_NAME = "SELECT ats, name, slug FROM companies WHERE name = ?"
SELECT_DISTINCT_SOURCES = (
    "SELECT DISTINCT watchlist FROM watchlists WHERE watchlist != '' ORDER BY watchlist"
)
SELECT_WATCHLISTS_BY_SOURCE = "SELECT * FROM watchlists WHERE watchlist = ? ORDER BY company_name"
PRAGMA_TABLE_INFO_JOBS = "PRAGMA table_info(jobs)"
PRAGMA_TABLE_INFO_JOBS_RECENT = "PRAGMA table_info(jobs_recent)"

JOBS_RECENT_TABLE = "jobs_recent"
DROP_JOBS_RECENT_TABLE = "DROP TABLE IF EXISTS jobs_recent"
DELETE_JOBS_RECENT = "DELETE FROM jobs_recent"

CREATE_JOBS_RECENT_TABLE = """
CREATE TABLE IF NOT EXISTS jobs_recent (
    global_id TEXT PRIMARY KEY,
    url TEXT NOT NULL,
    title TEXT NOT NULL,
    company TEXT NOT NULL,
    ats_type TEXT NOT NULL,
    ats_id TEXT,
    location TEXT,
    country_iso TEXT,
    region TEXT,
    lat REAL,
    lon REAL,
    is_remote INTEGER,
    salary_currency TEXT,
    salary_period TEXT,
    salary_summary TEXT,
    salary_min REAL,
    salary_max REAL,
    experience INTEGER,
    employment_type TEXT,
    department TEXT,
    team TEXT,
    requisition_id TEXT,
    apply_url TEXT,
    commitment TEXT,
    description TEXT,
    posted_at TEXT,
    fetched_at TEXT,
    language TEXT,
    raw TEXT
)
"""

CREATE_TRIGGER_JOBS_INSERT_RECENT = """
CREATE TRIGGER IF NOT EXISTS trg_jobs_after_insert
AFTER INSERT ON jobs
WHEN NEW.posted_at IS NOT NULL AND NEW.posted_at >= replace(datetime('now', '-24 hours'), ' ', 'T')
BEGIN
    INSERT OR IGNORE INTO jobs_recent VALUES (
        NEW.global_id, NEW.url, NEW.title, NEW.company, NEW.ats_type,
        NEW.ats_id, NEW.location, NEW.country_iso, NEW.region, NEW.lat,
        NEW.lon, NEW.is_remote, NEW.salary_currency, NEW.salary_period,
        NEW.salary_summary, NEW.salary_min, NEW.salary_max, NEW.experience,
        NEW.employment_type, NEW.department, NEW.team, NEW.requisition_id,
        NEW.apply_url, NEW.commitment, NEW.description, NEW.posted_at,
        NEW.fetched_at, NEW.language, NEW.raw
    );
END;
"""

CREATE_TRIGGER_JOBS_UPDATE_RECENT = """
CREATE TRIGGER IF NOT EXISTS trg_jobs_after_update
AFTER UPDATE ON jobs
BEGIN
    DELETE FROM jobs_recent
    WHERE global_id = NEW.global_id
      AND (NEW.posted_at IS NULL OR NEW.posted_at < replace(datetime('now', '-24 hours'), ' ', 'T'));

    INSERT OR REPLACE INTO jobs_recent
    SELECT NEW.global_id, NEW.url, NEW.title, NEW.company, NEW.ats_type,
           NEW.ats_id, NEW.location, NEW.country_iso, NEW.region, NEW.lat,
           NEW.lon, NEW.is_remote, NEW.salary_currency, NEW.salary_period,
           NEW.salary_summary, NEW.salary_min, NEW.salary_max, NEW.experience,
           NEW.employment_type, NEW.department, NEW.team, NEW.requisition_id,
           NEW.apply_url, NEW.commitment, NEW.description, NEW.posted_at,
           NEW.fetched_at, NEW.language, NEW.raw
    WHERE NEW.posted_at IS NOT NULL AND NEW.posted_at >= replace(datetime('now', '-24 hours'), ' ', 'T');
END;
"""

CREATE_TRIGGER_JOBS_DELETE_RECENT = """
CREATE TRIGGER IF NOT EXISTS trg_jobs_after_delete
AFTER DELETE ON jobs
BEGIN
    DELETE FROM jobs_recent WHERE global_id = OLD.global_id;
END;
"""

# --- Jobs-recent pruning ---
DELETE_JOBS_RECENT_STALE = (
    "DELETE FROM jobs_recent WHERE posted_at < replace(datetime('now', '-24 hours'), ' ', 'T')"
)

# --- Pruning ---
SELECT_WATCHLISTS_COUNT = "SELECT COUNT(*) FROM watchlists"
SELECT_UNWATCHED_COMPANIES_COUNT = (
    "SELECT COUNT(*) FROM companies c "
    "WHERE NOT EXISTS ("
    "SELECT 1 FROM watchlists w "
    "WHERE w.ats = c.ats AND w.company_slug = c.slug"
    ")"
)
DELETE_UNWATCHED_COMPANIES = (
    "DELETE FROM companies WHERE (ats, slug) NOT IN (SELECT ats, company_slug FROM watchlists)"
)


# --- Data queries ---
SELECT_DISTINCT_COMPANIES = "SELECT DISTINCT company FROM jobs ORDER BY company"
DELETE_COMPANIES = "DELETE FROM companies"
INSERT_ATS_FROM_COMPANIES = (
    "INSERT INTO ats (ats, name, slug) SELECT DISTINCT ats, ats, ats FROM companies ORDER BY ats"
)
SELECT_DISTINCT_ATS_TYPES = 'SELECT DISTINCT ats_type FROM "jobs" ORDER BY ats_type'

# --- Dynamic SQL templates ---
INSERT_JOBS_TEMPLATE = 'INSERT OR IGNORE INTO "{table}" ({columns}) VALUES {placeholders}'
SELECT_JOBS_COLUMNS_TEMPLATE = 'SELECT {columns} FROM "{table}"'
SELECT_JOBS_BY_COMPANY_TEMPLATE = (
    'SELECT {columns} FROM "{table}" WHERE company = ? ORDER BY company'
)
SELECT_JOBS_SINCE_TEMPLATE = 'SELECT {columns} FROM "{table}" WHERE posted_at >= ?'
SELECT_JOBS_BY_ATS_TEMPLATE = 'SELECT {columns} FROM "{table}" WHERE ats_type = ?'
SELECT_JOBS_BY_COMPANY_THIN_TEMPLATE = (
    'SELECT {columns} FROM "{table}" WHERE company = ? ORDER BY posted_at DESC'
)
SELECT_JOBS_SINCE_THIN_TEMPLATE = (
    'SELECT {columns} FROM "{table}" WHERE posted_at >= ? ORDER BY posted_at DESC'
)
SELECT_JOBS_BY_ATS_THIN_TEMPLATE = (
    'SELECT {columns} FROM "{table}" WHERE ats_type = ? ORDER BY posted_at DESC'
)
CREATE_TABLE_TEMPLATE = 'CREATE TABLE IF NOT EXISTS "{table_name}" ({column_defs})'
INSERT_INTO_TABLE_TEMPLATE = (
    'INSERT OR IGNORE INTO "{table_name}" ({columns}) VALUES {placeholders}'
)
SELECT_JOBS_BY_COMPANIES_TEMPLATE = (
    "SELECT * FROM jobs WHERE company IN ({placeholders}) ORDER BY company"
)
PRAGMA_TABLE_INFO_TEMPLATE = 'PRAGMA table_info("{table_name}")'
SELECT_ALL_FROM_TABLE_TEMPLATE = 'SELECT * FROM "{table_name}"'
INSERT_COMPANIES_BATCH_TEMPLATE = (
    "INSERT OR IGNORE INTO companies ({columns}) VALUES {placeholders}"
)

SELECT_COMPANIES_SLUG_URL = "SELECT slug, url FROM companies WHERE url IS NOT NULL AND url != ''"

# --- URL validation ---
SELECT_JOBS_FOR_VALIDATION = "SELECT global_id, url, apply_url, title FROM jobs"
SELECT_COMPANIES_FOR_VALIDATION = "SELECT rowid, name, slug, url FROM companies WHERE url IS NOT NULL AND url != '' ORDER BY RANDOM()"
DELETE_JOBS_BATCH_TEMPLATE = "DELETE FROM jobs WHERE global_id IN ({})"


class Database:
    JOBS_COLUMNS: ClassVar[list[str]] = [
        "global_id",
        "url",
        "title",
        "company",
        "ats_type",
        "ats_id",
        "location",
        "country_iso",
        "region",
        "lat",
        "lon",
        "is_remote",
        "salary_currency",
        "salary_period",
        "salary_summary",
        "salary_min",
        "salary_max",
        "experience",
        "employment_type",
        "department",
        "team",
        "requisition_id",
        "apply_url",
        "commitment",
        "description",
        "posted_at",
        "fetched_at",
        "language",
        "raw",
    ]

    JOBS_COLUMNS_THIN: ClassVar[list[str]] = [
        c for c in JOBS_COLUMNS if c not in ("description", "raw")
    ]

    _LOCAL_PATH = "data/database.db"

    # --- Connection ---

    @contextmanager
    def connect(self):
        connection = sqlite3.connect(self._LOCAL_PATH)
        try:
            yield connection
            connection.commit()
        except Exception:
            connection.rollback()
            raise
        finally:
            connection.close()

    # --- Initialization ---

    def initialize(self, connection):
        logger.info(operation="database_initialize_start")
        self.apply_performance_settings(connection)
        self.create_tables_ats(connection)
        self.create_table_companies(connection)
        self.create_table_jobs(connection)
        self.create_table_jobs_recent(connection)
        self.create_triggers_jobs_recent(connection)
        self.prune_jobs_recent(connection)
        self.create_table_watchlists(connection)
        self.create_index_companies_ats(connection)
        self.create_index_companies_slug(connection)
        self.create_index_companies_name(connection)
        self.create_index_companies_url(connection)

        self.create_index_jobs_company(connection)
        self.create_index_jobs_ats_type(connection)
        self.create_index_jobs_posted_at(connection)
        self.create_index_jobs_country_iso(connection)
        self.create_index_jobs_region(connection)
        self.create_index_jobs_language(connection)
        self.create_index_jobs_ats_type_posted_at(connection)
        self.create_index_jobs_company_posted_at(connection)
        self.create_index_jobs_recent_posted_at(connection)
        self.create_index_watchlists_watchlist(connection)
        self.create_view_junior_us_software(connection)
        self.create_view_us_software(connection)
        self.create_view_us_developer(connection)
        self.create_view_junior_us_developer(connection)
        self.create_view_us_frontend(connection)
        self.create_view_junior_us_software_24h(connection)
        self.create_view_us_software_24h(connection)
        self.create_view_us_developer_24h(connection)
        self.create_view_junior_us_developer_24h(connection)
        self.create_view_us_frontend_24h(connection)
        self.create_index_ats_unique(connection)
        self.create_index_companies_unique(connection)
        self.load_companies_from_parquet(connection)
        self.build_ats_from_companies(connection)
        self.load_watchlists_dir(connection, "data/parquet/watchlist")
        logger.info(
            operation="database_initialize_done",
            companies_seeded=self.company_count(connection),
        )

    # --- Schema ---

    def is_jobs_recent_table_stale(self, connection) -> bool:
        try:
            columns = [r[1] for r in connection.execute(PRAGMA_TABLE_INFO_JOBS_RECENT).fetchall()]
            return columns != self.JOBS_COLUMNS
        except Exception as exc:
            logger.error(operation="jobs_recent_table_stale_check", error=str(exc))
            return False

    def create_tables_ats(self, connection):
        try:
            connection.execute(DROP_ATS_TABLE)
            connection.execute(CREATE_ATS_TABLE)
        except Exception as exc:
            logger.error(operation="create_tables_ats", error=str(exc))
            raise

    def create_table_jobs(self, connection):
        try:
            connection.execute(CREATE_JOBS_TABLE)
        except Exception as exc:
            logger.error(operation="create_table_jobs", error=str(exc))
            raise

    def create_table_jobs_recent(self, connection):
        try:
            if self.is_jobs_recent_table_stale(connection):
                connection.execute(DROP_JOBS_RECENT_TABLE)
            connection.execute(CREATE_JOBS_RECENT_TABLE)
        except Exception as exc:
            logger.error(operation="create_table_jobs_recent", error=str(exc))
            raise

    def create_triggers_jobs_recent(self, connection):
        try:
            connection.execute("DROP TRIGGER IF EXISTS trg_jobs_after_insert")
            connection.execute("DROP TRIGGER IF EXISTS trg_jobs_after_update")
            connection.execute("DROP TRIGGER IF EXISTS trg_jobs_after_delete")
            connection.execute(CREATE_TRIGGER_JOBS_INSERT_RECENT)
            connection.execute(CREATE_TRIGGER_JOBS_UPDATE_RECENT)
            connection.execute(CREATE_TRIGGER_JOBS_DELETE_RECENT)
        except Exception as exc:
            logger.error(operation="create_triggers_jobs_recent", error=str(exc))
            raise

    def create_table_companies(self, connection):
        try:
            connection.execute(CREATE_COMPANIES_TABLE)
        except Exception as exc:
            logger.error(operation="create_table_companies", error=str(exc))
            raise

    def create_table_watchlists(self, connection):
        try:
            connection.execute(DROP_WATCHLISTS_TABLE)
            connection.execute(CREATE_WATCHLISTS_TABLE)
        except Exception as exc:
            logger.error(operation="create_table_watchlists", error=str(exc))
            raise

    def create_index_companies_ats(self, connection):
        try:
            connection.execute(CREATE_INDEX_COMPANIES_ATS)
        except Exception as exc:
            logger.error(operation="create_index_companies_ats", error=str(exc))
            raise

    def create_index_companies_slug(self, connection):
        try:
            connection.execute(CREATE_INDEX_COMPANIES_SLUG)
        except Exception as exc:
            logger.error(operation="create_index_companies_slug", error=str(exc))
            raise

    def create_index_companies_name(self, connection):
        try:
            connection.execute(CREATE_INDEX_COMPANIES_NAME)
        except Exception as exc:
            logger.error(operation="create_index_companies_name", error=str(exc))
            raise

    def create_index_jobs_company(self, connection):
        try:
            connection.execute(CREATE_INDEX_JOBS_COMPANY)
        except Exception as exc:
            logger.error(operation="create_index_jobs_company", error=str(exc))
            raise

    def create_index_jobs_ats_type(self, connection):
        try:
            connection.execute(CREATE_INDEX_JOBS_ATS_TYPE)
        except Exception as exc:
            logger.error(operation="create_index_jobs_ats_type", error=str(exc))
            raise

    def create_index_jobs_posted_at(self, connection):
        try:
            connection.execute(CREATE_INDEX_JOBS_POSTED_AT)
        except Exception as exc:
            logger.error(operation="create_index_jobs_posted_at", error=str(exc))
            raise

    def create_index_jobs_recent_posted_at(self, connection):
        try:
            connection.execute(CREATE_INDEX_JOBS_RECENT_POSTED_AT)
        except Exception as exc:
            logger.error(operation="create_index_jobs_recent_posted_at", error=str(exc))
            raise

    def prune_jobs_recent(self, connection):
        try:
            connection.execute(DELETE_JOBS_RECENT_STALE)
        except Exception as exc:
            logger.error(operation="prune_jobs_recent", error=str(exc))
            raise

    def create_index_watchlists_watchlist(self, connection):
        try:
            connection.execute(CREATE_INDEX_WATCHLISTS_WATCHLIST)
        except Exception as exc:
            logger.error(operation="create_index_watchlists_watchlist", error=str(exc))
            raise

    def create_index_companies_unique(self, connection):
        try:
            connection.execute(CREATE_UNIQUE_INDEX_COMPANIES)
        except Exception as exc:
            logger.error(operation="create_index_companies_unique", error=str(exc))
            raise

    def create_index_ats_unique(self, connection):
        try:
            connection.execute(CREATE_UNIQUE_INDEX_ATS)
        except Exception as exc:
            logger.error(operation="create_index_ats_unique", error=str(exc))
            raise

    def create_index_jobs_country_iso(self, connection):
        try:
            connection.execute(CREATE_INDEX_JOBS_COUNTRY_ISO)
        except Exception as exc:
            logger.error(operation="create_index_jobs_country_iso", error=str(exc))
            raise

    def create_index_jobs_region(self, connection):
        try:
            connection.execute(CREATE_INDEX_JOBS_REGION)
        except Exception as exc:
            logger.error(operation="create_index_jobs_region", error=str(exc))
            raise

    def create_index_jobs_language(self, connection):
        try:
            connection.execute(CREATE_INDEX_JOBS_LANGUAGE)
        except Exception as exc:
            logger.error(operation="create_index_jobs_language", error=str(exc))
            raise

    def create_index_jobs_ats_type_posted_at(self, connection):
        try:
            connection.execute(CREATE_INDEX_JOBS_ATS_TYPE_POSTED_AT)
        except Exception as exc:
            logger.error(operation="create_index_jobs_ats_type_posted_at", error=str(exc))
            raise

    def create_index_jobs_company_posted_at(self, connection):
        try:
            connection.execute(CREATE_INDEX_JOBS_COMPANY_POSTED_AT)
        except Exception as exc:
            logger.error(operation="create_index_jobs_company_posted_at", error=str(exc))
            raise

    def create_index_companies_url(self, connection):
        try:
            connection.execute(CREATE_INDEX_COMPANIES_URL)
        except Exception as exc:
            logger.error(operation="create_index_companies_url", error=str(exc))
            raise

    # --- Watchlist-based pruning ---

    def prune_unwatched_companies(self, connection, dry_run: bool = False) -> int:
        try:
            watchlist_count = connection.execute(SELECT_WATCHLISTS_COUNT).fetchone()[0]

            if watchlist_count == 0 and not dry_run:
                logger.warning(
                    operation="prune_unwatched_companies",
                    message="watchlists table is empty — not pruning",
                )
                return 0

            count = connection.execute(SELECT_UNWATCHED_COMPANIES_COUNT).fetchone()[0]

            if count and not dry_run:
                connection.execute(DELETE_UNWATCHED_COMPANIES)

            logger.info(
                operation="prune_unwatched_companies",
                removed=count,
                dry_run=dry_run,
            )
            return count
        except Exception as exc:
            logger.error(operation="prune_unwatched_companies", error=str(exc))
            raise

    # --- URL validation ---

    def validate_job_urls(self, connection, max_workers: int = 20, dry_run: bool = False):
        try:
            import concurrent.futures
            import random

            import httpx

            rows = connection.execute(SELECT_JOBS_FOR_VALIDATION).fetchall()
            random.shuffle(rows)
            total = len(rows)
            passed = 0
            failed = 0
            failed_ids: list[str] = []

            def _check(row: tuple) -> tuple[bool, str | None]:
                _gid, url, apply_url, title = row
                try:
                    resp_head = httpx.head(url, timeout=10.0, follow_redirects=True)
                    if not resp_head.is_success:
                        return (False, f"HEAD {resp_head.status_code}")

                    resp_get = httpx.get(url, timeout=10.0, follow_redirects=True)
                    if not resp_get.is_success:
                        return (False, f"GET {resp_get.status_code}")
                    if title.lower() not in resp_get.text.lower():
                        return (False, "title not found in page body")

                    if apply_url and apply_url != url:
                        resp_apply = httpx.head(apply_url, timeout=10.0, follow_redirects=True)
                        if not resp_apply.is_success:
                            return (False, f"apply_url HEAD {resp_apply.status_code}")

                    return (True, None)
                except Exception as exc:
                    return (False, str(exc))

            with concurrent.futures.ThreadPoolExecutor(max_workers=max_workers) as pool:
                fut_to_row = {pool.submit(_check, r): r for r in rows}
                for count, fut in enumerate(concurrent.futures.as_completed(fut_to_row), start=1):
                    row = fut_to_row[fut]
                    ok, reason = fut.result()
                    if ok:
                        passed += 1
                        print(f"[{count}/{total}] [OK] {row[3]} — {row[1]}")
                    else:
                        failed += 1
                        failed_ids.append(row[0])
                        print(f"[{count}/{total}] [FAIL] {row[3]} — {row[1]} ({reason})")
                        logger.error(
                            operation="validate_job_urls_failure",
                            global_id=row[0],
                            url=row[1],
                            title=row[3],
                            reason=reason or "unknown",
                        )

            if failed_ids and not dry_run:
                for i in range(0, len(failed_ids), 500):
                    batch = failed_ids[i : i + 500]
                    placeholders = ",".join("?" for _ in batch)
                    connection.execute(DELETE_JOBS_BATCH_TEMPLATE.format(placeholders), batch)
                removed = len(failed_ids)
            else:
                removed = 0

            logger.info(
                operation="validate_job_urls",
                total=total,
                passed=passed,
                failed=failed,
                removed=removed,
                dry_run=dry_run,
            )
            return passed, failed, total
        except Exception as exc:
            logger.error(operation="validate_job_urls", error=str(exc))
            raise

    def validate_company_urls(self, connection, max_workers: int = 20, dry_run: bool = False):
        try:
            import concurrent.futures
            import random

            import httpx

            rows = connection.execute(SELECT_COMPANIES_FOR_VALIDATION).fetchall()
            random.shuffle(rows)
            total = len(rows)
            passed = 0
            failed = 0
            skipped = 0

            def _check(row: tuple) -> tuple[str, str | None]:
                _rid, name, _slug, url = row
                try:
                    resp_head = httpx.head(url, timeout=10.0, follow_redirects=True)
                    if not resp_head.is_success:
                        if resp_head.status_code in (404, 410):
                            return ("delete", f"HEAD {resp_head.status_code}")
                        return ("skip", f"HEAD {resp_head.status_code}")

                    resp_get = httpx.get(url, timeout=10.0, follow_redirects=True)
                    if not resp_get.is_success:
                        if resp_get.status_code in (404, 410):
                            return ("delete", f"GET {resp_get.status_code}")
                        return ("skip", f"GET {resp_get.status_code}")
                    if name.lower() not in resp_get.text.lower():
                        return ("delete", "company name not found in page body")

                    return ("ok", None)
                except httpx.TimeoutException as exc:
                    return ("skip", f"timeout: {exc}")
                except httpx.NetworkError as exc:
                    return ("skip", f"network error: {exc}")
                except httpx.HTTPError as exc:
                    return ("skip", f"HTTP error: {exc}")
                except Exception as exc:
                    return ("skip", str(exc))

            with concurrent.futures.ThreadPoolExecutor(max_workers=max_workers) as pool:
                fut_to_row = {pool.submit(_check, r): r for r in rows}
                for count, fut in enumerate(concurrent.futures.as_completed(fut_to_row), start=1):
                    row = fut_to_row[fut]
                    status, reason = fut.result()
                    if status == "ok":
                        passed += 1
                        print(f"[{count}/{total}] [OK] {row[1]} — {row[3]}")
                    elif status == "delete" and not dry_run:
                        failed += 1
                        connection.execute("DELETE FROM companies WHERE rowid = ?", (row[0],))
                        connection.commit()
                        print(f"[{count}/{total}] [FAIL] {row[1]} — {row[3]} ({reason})")
                        logger.error(
                            operation="validate_company_urls_failure",
                            company=row[1],
                            url=row[3],
                            reason=reason or "unknown",
                        )
                    else:
                        skipped += 1
                        print(f"[{count}/{total}] [SKIP] {row[1]} — {row[3]} ({reason})")

            removed = failed

            logger.info(
                operation="validate_company_urls",
                total=total,
                passed=passed,
                failed=failed,
                skipped=skipped,
                removed=removed,
                dry_run=dry_run,
            )
            return passed, failed, skipped, total
        except Exception as exc:
            logger.error(operation="validate_company_urls", error=str(exc))
            raise

    # --- Views ---

    def create_view_junior_us_software(self, connection):
        try:
            connection.execute(CREATE_VIEW_JUNIOR_US_SOFTWARE)
        except Exception as exc:
            logger.error(operation="create_view_junior_us_software", error=str(exc))
            raise

    def create_view_us_software(self, connection):
        try:
            connection.execute(CREATE_VIEW_US_SOFTWARE)
        except Exception as exc:
            logger.error(operation="create_view_us_software", error=str(exc))
            raise

    def create_view_us_developer(self, connection):
        try:
            connection.execute(CREATE_VIEW_US_DEVELOPER)
        except Exception as exc:
            logger.error(operation="create_view_us_developer", error=str(exc))
            raise

    def create_view_junior_us_developer(self, connection):
        try:
            connection.execute(CREATE_VIEW_JUNIOR_US_DEVELOPER)
        except Exception as exc:
            logger.error(operation="create_view_junior_us_developer", error=str(exc))
            raise

    def create_view_us_frontend(self, connection):
        try:
            connection.execute(CREATE_VIEW_US_FRONTEND)
        except Exception as exc:
            logger.error(operation="create_view_us_frontend", error=str(exc))
            raise

    def create_view_junior_us_software_24h(self, connection):
        try:
            connection.execute(CREATE_VIEW_JUNIOR_US_SOFTWARE_24H)
        except Exception as exc:
            logger.error(operation="create_view_junior_us_software_24h", error=str(exc))
            raise

    def create_view_us_software_24h(self, connection):
        try:
            connection.execute(CREATE_VIEW_US_SOFTWARE_24H)
        except Exception as exc:
            logger.error(operation="create_view_us_software_24h", error=str(exc))
            raise

    def create_view_us_developer_24h(self, connection):
        try:
            connection.execute(CREATE_VIEW_US_DEVELOPER_24H)
        except Exception as exc:
            logger.error(operation="create_view_us_developer_24h", error=str(exc))
            raise

    def create_view_junior_us_developer_24h(self, connection):
        try:
            connection.execute(CREATE_VIEW_JUNIOR_US_DEVELOPER_24H)
        except Exception as exc:
            logger.error(operation="create_view_junior_us_developer_24h", error=str(exc))
            raise

    def create_view_us_frontend_24h(self, connection):
        try:
            connection.execute(CREATE_VIEW_US_FRONTEND_24H)
        except Exception as exc:
            logger.error(operation="create_view_us_frontend_24h", error=str(exc))
            raise

    def apply_performance_settings(self, connection):
        try:
            connection.execute(PRAGMA_JOURNAL_WAL)
            connection.execute(PRAGMA_SYNCHRONOUS_NORMAL)
            connection.execute(PRAGMA_CACHE_SIZE)
            connection.execute(PRAGMA_BUSY_TIMEOUT)
            connection.execute(PRAGMA_TEMP_STORE)
            connection.execute(PRAGMA_MMAP_SIZE)
        except Exception as exc:
            logger.error(operation="apply_pragmas", error=str(exc))

    # --- Data ---

    def insert_jobs(self, connection, jobs):
        try:
            cols = self.JOBS_COLUMNS
            col_names = ",".join(f'"{c}"' for c in cols)
            ncols = len(cols)
            for i in range(0, len(jobs), 500):
                batch = jobs[i : i + 500]
                placeholders = ",".join(
                    f"({','.join('?' for _ in range(ncols))})" for _ in range(len(batch))
                )
                flat = [row.get(c) for row in batch for c in cols]
                connection.execute(
                    INSERT_JOBS_TEMPLATE.format(
                        table=JOBS_TABLE, columns=col_names, placeholders=placeholders
                    ),
                    flat,
                )
        except Exception as exc:
            logger.error(operation="insert_jobs", error=str(exc), exc_type=type(exc).__name__)
            raise

    def read_all_jobs(self, connection):
        try:
            cols = self.JOBS_COLUMNS
            col_names = ",".join(f'"{c}"' for c in cols)
            rows = connection.execute(
                SELECT_JOBS_COLUMNS_TEMPLATE.format(columns=col_names, table=JOBS_TABLE)
            ).fetchall()
            return [dict(zip(cols, row, strict=True)) for row in rows]
        except Exception as exc:
            logger.error(operation="read_all_jobs", error=str(exc))
            raise

    def read_distinct_companies(self, connection) -> list[str]:
        try:
            rows = connection.execute(SELECT_DISTINCT_COMPANIES).fetchall()
            return [r[0] for r in rows if r[0]]
        except Exception as exc:
            logger.error(operation="read_distinct_companies", error=str(exc))
            raise

    def read_companies_slug_url(self, connection) -> list[tuple[str, str]]:
        try:
            return list(connection.execute(SELECT_COMPANIES_SLUG_URL).fetchall())
        except Exception as exc:
            logger.error(operation="read_companies_slug_url", error=str(exc))
            raise

    def read_jobs_for_company(self, connection, company: str):
        try:
            cols = self.JOBS_COLUMNS
            col_names = ",".join(f'"{c}"' for c in cols)
            rows = connection.execute(
                SELECT_JOBS_BY_COMPANY_TEMPLATE.format(columns=col_names, table=JOBS_TABLE),
                (company,),
            ).fetchall()
            return [dict(zip(cols, row, strict=True)) for row in rows]
        except Exception as exc:
            logger.error(operation="read_jobs_for_company", company=company, error=str(exc))
            raise

    def read_jobs_since(self, connection, hours: int = 24):
        try:
            cols = self.JOBS_COLUMNS
            col_names = ",".join(f'"{c}"' for c in cols)
            cutoff = (datetime.now(UTC) - timedelta(hours=hours)).isoformat()
            rows = connection.execute(
                SELECT_JOBS_SINCE_TEMPLATE.format(columns=col_names, table=JOBS_TABLE),
                (cutoff,),
            ).fetchall()
            return [dict(zip(cols, row, strict=True)) for row in rows]
        except Exception as exc:
            logger.error(operation="read_jobs_since", hours=hours, error=str(exc))
            raise

    def read_all_jobs_iter(self, connection, batch_size: int = 10000):
        try:
            cols = self.JOBS_COLUMNS
            col_names = ",".join(f'"{c}"' for c in cols)
            cursor = connection.execute(
                SELECT_JOBS_COLUMNS_TEMPLATE.format(columns=col_names, table=JOBS_TABLE)
            )
            while True:
                rows = cursor.fetchmany(batch_size)
                if not rows:
                    break
                yield [dict(zip(cols, row, strict=True)) for row in rows]
        except Exception as exc:
            logger.error(operation="read_all_jobs_iter", error=str(exc))
            raise

    def read_jobs_since_iter(self, connection, hours: int = 24, batch_size: int = 10000):
        try:
            cols = self.JOBS_COLUMNS
            col_names = ",".join(f'"{c}"' for c in cols)
            cutoff = (datetime.now(UTC) - timedelta(hours=hours)).isoformat()
            cursor = connection.execute(
                SELECT_JOBS_SINCE_TEMPLATE.format(columns=col_names, table=JOBS_TABLE),
                (cutoff,),
            )
            while True:
                rows = cursor.fetchmany(batch_size)
                if not rows:
                    break
                yield [dict(zip(cols, row, strict=True)) for row in rows]
        except Exception as exc:
            logger.error(operation="read_jobs_since_iter", hours=hours, error=str(exc))
            raise

    def read_jobs_recent_iter(self, connection, batch_size: int = 10000):
        try:
            cols = self.JOBS_COLUMNS
            col_names = ",".join(f'"{c}"' for c in cols)
            cursor = connection.execute(
                f'SELECT {col_names} FROM "{JOBS_RECENT_TABLE}"',
            )
            while True:
                rows = cursor.fetchmany(batch_size)
                if not rows:
                    break
                yield [dict(zip(cols, row, strict=True)) for row in rows]
        except Exception as exc:
            logger.error(operation="read_jobs_recent_iter", error=str(exc))
            raise

    def read_companies_ats(self, connection):
        try:
            companies_by_ats: dict[ATSType, list[dict[str, str]]] = {}
            for ats_name, name, slug, url in connection.execute(SELECT_COMPANIES_ATS).fetchall():
                try:
                    ats_type = ATSType(ats_name)
                except ValueError:
                    pass
                else:
                    companies_by_ats.setdefault(ats_type, []).append(
                        {"name": name, "slug": slug, "url": url or slug}
                    )
            return companies_by_ats
        except Exception as exc:
            logger.error(operation="read_companies_ats", error=str(exc))
            raise

    def read_companies_no_ats(self, connection):
        try:
            unknown_ats: list[str] = []
            for ats_name, _name, _slug, _url in connection.execute(SELECT_COMPANIES_ATS).fetchall():
                try:
                    ATSType(ats_name)
                except ValueError:
                    unknown_ats.append(ats_name)
            return unknown_ats
        except Exception as exc:
            logger.error(operation="read_companies_no_ats", error=str(exc))
            raise

    def read_companies_table(self, connection):
        try:
            rows = connection.execute(SELECT_ALL_COMPANIES).fetchall()
            return [{"ats": r[0], "name": r[1], "slug": r[2], "url": r[3]} for r in rows]
        except Exception as exc:
            logger.error(operation="read_companies_table", error=str(exc))
            raise

    def read_ats_table(self, connection):
        try:
            rows = connection.execute(SELECT_ALL_ATS).fetchall()
            return [{"ats": r[0], "name": r[1], "slug": r[2]} for r in rows]
        except Exception as exc:
            logger.error(operation="read_ats_table", error=str(exc))
            raise

    def company_count(self, connection) -> int:
        try:
            return connection.execute(SELECT_COMPANIES_COUNT).fetchone()[0]
        except Exception as exc:
            logger.error(operation="company_count", error=str(exc))
            raise

    def load_companies_from_parquet(self, connection, path: str = "data/parquet/companies.parquet"):
        try:
            import pyarrow.parquet as pq

            connection.execute(DELETE_COMPANIES)
            table = pq.read_table(path)
            cols = table.column_names
            rows = table.to_pydict()
            n_rows = table.num_rows
            if n_rows == 0:
                return
            ncols = len(cols)
            row_dicts = [
                dict(zip(cols, vals, strict=True))
                for vals in zip(*[rows[c] for c in cols], strict=True)
            ]
            for i in range(0, n_rows, 500):
                batch = row_dicts[i : i + 500]
                placeholders = ",".join(
                    f"({','.join('?' for _ in range(ncols))})" for _ in range(len(batch))
                )
                flat = [row[c] for row in batch for c in cols]
                connection.execute(
                    INSERT_COMPANIES_BATCH_TEMPLATE.format(
                        columns=",".join(cols), placeholders=placeholders
                    ),
                    flat,
                )
            logger.info(operation="load_companies_from_parquet", path=path, rows=n_rows)
        except Exception as exc:
            logger.error(operation="load_companies_from_parquet", path=path, error=str(exc))
            raise

    def build_ats_from_companies(self, connection):
        try:
            connection.execute(INSERT_ATS_FROM_COMPANIES)
        except Exception as exc:
            logger.error(operation="build_ats_from_companies", error=str(exc))
            raise

    def load_all_parquet(self, connection, directory: str = "data/parquet/companies_by_ats"):
        try:
            import glob
            import os

            import pyarrow.parquet as pq

            for parquet_path in sorted(glob.glob(os.path.join(directory, "*.parquet"))):
                table_name = os.path.splitext(os.path.basename(parquet_path))[0]

                table = pq.read_table(parquet_path)
                cols = table.column_names
                rows = table.to_pydict()
                n_rows = table.num_rows

                if n_rows == 0:
                    continue

                col_defs = ",".join(f'"{c}" TEXT' for c in cols)
                connection.execute(
                    CREATE_TABLE_TEMPLATE.format(table_name=table_name, column_defs=col_defs)
                )
                col_names = ",".join(f'"{c}"' for c in cols)
                ncols = len(cols)

                row_dicts = [
                    dict(zip(cols, vals, strict=True))
                    for vals in zip(*[rows[c] for c in cols], strict=True)
                ]

                for i in range(0, n_rows, 500):
                    batch = row_dicts[i : i + 500]
                    placeholders = ",".join(
                        f"({','.join('?' for _ in range(ncols))})" for _ in range(len(batch))
                    )
                    flat = [row[c] for row in batch for c in cols]
                    connection.execute(
                        INSERT_INTO_TABLE_TEMPLATE.format(
                            table_name=table_name, columns=col_names, placeholders=placeholders
                        ),
                        flat,
                    )

                logger.info(
                    operation="load_parquet",
                    table=table_name,
                    path=parquet_path,
                    rows=n_rows,
                )
        except Exception as exc:
            logger.error(
                operation="load_all_parquet",
                directory=directory,
                error=str(exc),
                exc_type=type(exc).__name__,
            )
            raise

    def delete_jobs_table(self, connection):
        try:
            connection.execute(DELETE_JOBS)
        except Exception as exc:
            logger.error(operation="delete_jobs_table", error=str(exc))
            raise

    # --- Watchlist ---

    def _insert_watchlist(
        self, connection, ats: str, company_name: str, company_slug: str, source: str = ""
    ):
        try:
            connection.execute(INSERT_WATCHLIST, (ats, company_name, company_slug, source))
        except Exception as exc:
            logger.error(operation="insert_watchlist", error=str(exc))
            raise

    def clear_watchlists(self, connection):
        try:
            connection.execute(CLEAR_WATCHLISTS)
        except Exception as exc:
            logger.error(operation="clear_watchlists", error=str(exc))
            raise

    def load_watchlists_dir(self, connection, directory: str):
        import glob
        import os

        import pyarrow.parquet as pq

        try:
            self.clear_watchlists(connection)
            total_matched = 0
            for parquet_path in sorted(glob.glob(os.path.join(directory, "*.parquet"))):
                source = os.path.splitext(os.path.basename(parquet_path))[0]
                table = pq.read_table(parquet_path)
                rows_dict = table.to_pydict()
                names = [
                    rows_dict["name"][i] for i in range(table.num_rows) if rows_dict["name"][i]
                ]
                matched = 0
                for name in names:
                    for ats, cname, slug in connection.execute(
                        SELECT_COMPANIES_BY_NAME, (name,)
                    ).fetchall():
                        self._insert_watchlist(connection, ats, cname, slug, source)
                        matched += 1
                total_matched += matched
                logger.info(
                    operation="load_watchlists_parquet",
                    source=source,
                    names=len(names),
                    matched=matched,
                )
            logger.info(
                operation="load_watchlists_dir",
                path=directory,
                matched=total_matched,
            )
        except Exception as exc:
            logger.error(operation="load_watchlists_dir", path=directory, error=str(exc))

    def read_watchlists(self, connection):
        try:
            rows = connection.execute(SELECT_WATCHLISTS).fetchall()
            return [
                {
                    "ats": r[0],
                    "company_name": r[1],
                    "company_slug": r[2],
                    "watchlist": r[3],
                    "created_at": r[4],
                }
                for r in rows
            ]
        except Exception as exc:
            logger.error(operation="read_watchlists", error=str(exc))
            raise

    def read_watchlist_sources(self, connection):
        try:
            rows = connection.execute(SELECT_DISTINCT_SOURCES).fetchall()
            return [r[0] for r in rows]
        except Exception as exc:
            logger.error(operation="read_watchlist_sources", error=str(exc))
            raise

    def read_watchlists_by_source(self, connection, source: str):
        try:
            rows = connection.execute(SELECT_WATCHLISTS_BY_SOURCE, (source,)).fetchall()
            return [
                {
                    "ats": r[0],
                    "company_name": r[1],
                    "company_slug": r[2],
                    "watchlist": r[3],
                    "created_at": r[4],
                }
                for r in rows
            ]
        except Exception as exc:
            logger.error(operation="read_watchlists_by_source", source=source, error=str(exc))
            raise

    def is_in_watchlist(self, connection, ats: str, company_slug: str) -> bool:
        try:
            row = connection.execute(SELECT_WATCHLIST_CHECK, (ats, company_slug)).fetchone()
            return row[0] > 0
        except Exception as exc:
            logger.error(operation="is_in_watchlist", error=str(exc))
            raise

    def dump_watchlist_jobs(self, connection, source: str) -> int:
        try:
            import os

            rows = connection.execute(SELECT_WATCHLISTS_BY_SOURCE, (source,)).fetchall()
            companies = list(dict.fromkeys(r[1] for r in rows))
            if not companies:
                logger.info(operation="dump_watchlist_jobs", source=source, jobs=0)
                return 0
            placeholders = ",".join("?" for _ in companies)
            jobs = connection.execute(
                SELECT_JOBS_BY_COMPANIES_TEMPLATE.format(placeholders=placeholders),
                companies,
            ).fetchall()
            cols = self.JOBS_COLUMNS
            job_rows = [dict(zip(cols, r, strict=True)) for r in jobs]
            parquet_dir = "data/parquet/jobs_by_watchlist"
            os.makedirs(parquet_dir, exist_ok=True)
            self._write_table_parquet(job_rows, f"{parquet_dir}/{source}.parquet")
            logger.info(
                operation="dump_watchlist_jobs",
                source=source,
                companies=len(companies),
                jobs=len(job_rows),
            )
            return len(job_rows)
        except Exception as exc:
            logger.error(operation="dump_watchlist_jobs", source=source, error=str(exc))
            return 0

    def read_jobs_for_ats(self, connection, ats_type: str):
        try:
            cols = self.JOBS_COLUMNS
            col_names = ",".join(f'"{c}"' for c in cols)
            rows = connection.execute(
                SELECT_JOBS_BY_ATS_TEMPLATE.format(columns=col_names, table=JOBS_TABLE),
                (ats_type,),
            ).fetchall()
            return [dict(zip(cols, row, strict=True)) for row in rows]
        except Exception as exc:
            logger.error(operation="read_jobs_for_ats", ats_type=ats_type, error=str(exc))
            raise

    def dump_jobs_by_ats(self, connection, ats_types: list[str] | None = None) -> None:
        import os

        try:
            if ats_types is None:
                rows = connection.execute(SELECT_DISTINCT_ATS_TYPES).fetchall()
                ats_types = [r[0] for r in rows if r[0]]
            if not ats_types:
                logger.info(operation="dump_jobs_by_ats", rows=0)
                return
            parquet_dir = "data/parquet/jobs_by_ats"
            os.makedirs(parquet_dir, exist_ok=True)
            total_rows = 0
            for ats_type in ats_types:
                rows = self.read_jobs_for_ats(connection, ats_type)
                if not rows:
                    continue
                slug = re.sub(r"[^a-zA-Z0-9]+", "-", ats_type).strip("-").lower() or "unknown"
                parquet_path = f"{parquet_dir}/{slug}.parquet"
                self._write_table_parquet(rows, parquet_path)
                total_rows += len(rows)
                logger.info(
                    operation="dump_jobs_by_ats",
                    ats_type=ats_type,
                    rows=len(rows),
                )
            logger.info(
                operation="dump_jobs_by_ats_done",
                ats_types=len(ats_types),
                total_rows=total_rows,
            )
        except Exception as exc:
            logger.error(operation="dump_jobs_by_ats", error=str(exc))
            raise

    # --- Thin read methods (exclude description, raw) ---

    def read_jobs_for_company_thin(self, connection, company: str):
        try:
            cols = self.JOBS_COLUMNS_THIN
            col_names = ",".join(f'"{c}"' for c in cols)
            rows = connection.execute(
                SELECT_JOBS_BY_COMPANY_THIN_TEMPLATE.format(columns=col_names, table=JOBS_TABLE),
                (company,),
            ).fetchall()
            return [dict(zip(cols, row, strict=True)) for row in rows]
        except Exception as exc:
            logger.error(operation="read_jobs_for_company_thin", company=company, error=str(exc))
            raise

    def read_jobs_since_thin(self, connection, hours: int = 24):
        try:
            cols = self.JOBS_COLUMNS_THIN
            col_names = ",".join(f'"{c}"' for c in cols)
            cutoff = (datetime.now(UTC) - timedelta(hours=hours)).isoformat()
            rows = connection.execute(
                SELECT_JOBS_SINCE_THIN_TEMPLATE.format(columns=col_names, table=JOBS_TABLE),
                (cutoff,),
            ).fetchall()
            return [dict(zip(cols, row, strict=True)) for row in rows]
        except Exception as exc:
            logger.error(operation="read_jobs_since_thin", hours=hours, error=str(exc))
            raise

    def read_jobs_for_ats_thin(self, connection, ats_type: str):
        try:
            cols = self.JOBS_COLUMNS_THIN
            col_names = ",".join(f'"{c}"' for c in cols)
            rows = connection.execute(
                SELECT_JOBS_BY_ATS_THIN_TEMPLATE.format(columns=col_names, table=JOBS_TABLE),
                (ats_type,),
            ).fetchall()
            return [dict(zip(cols, row, strict=True)) for row in rows]
        except Exception as exc:
            logger.error(operation="read_jobs_for_ats_thin", ats_type=ats_type, error=str(exc))
            raise

    # --- Internal helpers ---

    def _all_table_names(self, connection) -> list[str]:
        standard = ["companies", "ats", "jobs", "watchlists"]
        non_standard = [r[0] for r in connection.execute(SELECT_NON_STANDARD_TABLES).fetchall()]
        return standard + non_standard

    def _table_columns(self, connection, table_name: str) -> list[str]:
        try:
            return [
                r[1]
                for r in connection.execute(
                    PRAGMA_TABLE_INFO_TEMPLATE.format(table_name=table_name)
                ).fetchall()
            ]
        except Exception as exc:
            logger.error(operation="table_columns", table=table_name, error=str(exc))
            raise

    # --- Concrete template methods ---

    def dump_jobs_recent(self, connection, hours: int = 24) -> None:
        from database.parquet import ParquetBufferWriter

        self.prune_jobs_recent(connection)
        path = "data/parquet/jobs_recent.parquet"
        with ParquetBufferWriter(path) as writer:
            total = 0
            for batch in self.read_jobs_recent_iter(connection):
                writer.write_rows(batch)
                total += len(batch)
            if total == 0:
                logger.info(operation="dump_jobs_recent", hours=hours, rows=0)
                return
            logger.info(
                operation="dump_jobs_recent",
                hours=hours,
                rows=total,
            )

    def dump_jobs_by_company(self, connection, companies: list[str] | None = None) -> None:
        if companies is None:
            companies = self.read_distinct_companies(connection)
        if not companies:
            logger.info(operation="dump_jobs_by_company", rows=0)
            return
        parquet_dir = "data/parquet/jobs_by_company"
        os.makedirs(parquet_dir, exist_ok=True)
        total_rows = 0
        for company_name in companies:
            rows = self.read_jobs_for_company(connection, company_name)
            if not rows:
                continue
            slug = re.sub(r"[^a-zA-Z0-9]+", "-", company_name).strip("-").lower() or "unknown"
            parquet_path = f"{parquet_dir}/{slug}.parquet"
            self._write_table_parquet(rows, parquet_path)
            total_rows += len(rows)
            logger.info(
                operation="dump_jobs_by_company",
                company=company_name,
                slug=slug,
                rows=len(rows),
            )
        logger.info(
            operation="dump_jobs_by_company_done",
            companies=len(companies),
            total_rows=total_rows,
        )

    def dump_watchlist_all(self, connection) -> None:
        sources = self.read_watchlist_sources(connection)
        if not sources:
            logger.info(operation="dump_watchlist_all", rows=0)
            return
        total = 0
        for source in sources:
            count = self.dump_watchlist_jobs(connection, source)
            total += count
            logger.info(operation="dump_watchlist_all_source", source=source, jobs=count)
        logger.info(operation="dump_watchlist_all_done", sources=len(sources), total_jobs=total)

    def dump_all_tables(self, connection):
        for name in self._all_table_names(connection):
            if name == "jobs":
                self._dump_jobs_table_streamed(connection)
                continue
            rows = self._read_table_data(connection, name)
            if name in _STANDARD_TABLES:
                path = f"data/parquet/{name}.parquet"
            else:
                path = f"data/parquet/companies_by_ats/{name}.parquet"
            self._write_table_parquet(rows, path)
            logger.info(
                operation="dump_table",
                table=name,
                rows=len(rows),
            )

    def _dump_jobs_table_streamed(self, connection):
        from database.parquet import ParquetBufferWriter

        path = "data/parquet/jobs.parquet"
        with ParquetBufferWriter(path) as writer:
            total = 0
            for batch in self.read_all_jobs_iter(connection):
                writer.write_rows(batch)
                total += len(batch)
            logger.info(
                operation="dump_table",
                table="jobs",
                rows=total,
            )

    def dump_watch_table(self, connection) -> None:
        rows = self._read_table_data(connection, "watchlists")
        if not rows:
            logger.info(operation="dump_watch_table", rows=0)
            return
        self._write_table_parquet(rows, "data/parquet/watchlists.parquet")
        logger.info(operation="dump_watch_table", rows=len(rows))

    def _read_table_data(self, connection, name: str):
        cols = self._table_columns(connection, name)
        return [
            dict(zip(cols, row, strict=True))
            for row in connection.execute(
                SELECT_ALL_FROM_TABLE_TEMPLATE.format(table_name=name)
            ).fetchall()
        ]

    def _write_table_parquet(self, rows, path: str) -> None:
        from database.parquet import ParquetBufferWriter

        with ParquetBufferWriter(path) as writer:
            writer.write_rows(rows)

    def dump_all_companies(self, connection) -> None:
        rows = self._read_table_data(connection, "companies")
        if not rows:
            logger.info(operation="dump_all_companies", rows=0)
            return
        self._write_table_parquet(rows, "data/parquet/companies.parquet")
        logger.info(operation="dump_all_companies", rows=len(rows))

    def dump_all_ats_table(self, connection) -> None:
        rows = self._read_table_data(connection, "ats")
        if not rows:
            logger.info(operation="dump_all_ats_table", rows=0)
            return
        self._write_table_parquet(rows, "data/parquet/companies_table.parquet")
        logger.info(operation="dump_all_ats_table", rows=len(rows))

    def dump_ats_table(self, connection) -> None:
        rows = self._read_table_data(connection, "ats")
        if not rows:
            logger.info(operation="dump_all_ats_table", rows=0)
            return
        self._write_table_parquet(rows, "data/parquet/ats.parquet")
        logger.info(operation="dump_all_ats_table", rows=len(rows))


# --- Singleton ---

database: Database = Database()
