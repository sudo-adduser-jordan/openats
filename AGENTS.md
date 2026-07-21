# agents

## Commands

```
uv sync --extra dev
ruff check src/
mypy src/
ruff format src/
pylint src/
pytest
```

```
uv run openats                                    # runs full pipeline (collect all companies)
openats database                                  # create/reinitialize database schema + seed from parquet
openats collect [--skip ...]                      # collect all, optionally skipping ATS type(s)
openats collect company [companies...]            # collect jobs for specific company name(s) or slug(s)
openats collect ats [ats...] [--skip ...]         # collect jobs for all companies on given ATS type(s)
openats collect watchlist [watchlist] [--skip-ats ...]  # collect jobs for all watched companies
openats dump recent jobs                          # dump jobs posted in last 24 hours → data/parquet/jobs_recent.parquet
openats dump ats [ats...]                         # dump jobs grouped by ATS type → data/parquet/jobs_by_ats/{ats}.parquet
openats dump company [companies...]               # dump jobs grouped by company → data/parquet/jobs_by_company/{slug}.parquet
openats dump companies-table                      # dump full companies table → data/parquet/companies.parquet
openats dump ats-table                            # dump ats table → data/parquet/ats.parquet
openats dump watchlist-table                      # dump watchlists table → data/parquet/watchlists.parquet
openats dump watchlist [watchlist]                # dump jobs for watchlist source(s) → data/parquet/jobs_by_watchlist/{source}.parquet
openats watchlist load <path>                     # load watch list from parquet files in directory
openats watchlist list                            # list available watchlist titles
openats remove unwatched [--dry-run]              # remove companies not in any watchlist
openats validate jobs [--workers N] [--dry-run]   # check job URLs exist and titles match
openats validate companies [--workers N] [--dry-run]  # check company URLs exist and names match
```

## Project Context

- Pipeline collects job listings from **47 ATS types** across **86,000+ companies** (~3.27M live jobs) into SQLite
- Local SQLite is primary storage: `data/database.db` (from `DATABASE_PATH` env var)
- CLI: `openats database`, `openats collect`, `openats dump`, `openats watchlist`, `openats remove`, `openats validate`
- Per-ATS token bucket rate limiter (10 req/s) in `producer.py` — applies to all fetchers

## Schema

### `jobs` — canonical job listings

| Column | Type | Constraints | Notes |
|---|---|---|---|
| `global_id` | TEXT | PK NOT NULL | `{ats_type}:{ats_id}` or UUID4 fallback |
| `url` | TEXT | NOT NULL | Public posting URL |
| `title` | TEXT | NOT NULL | Free-form job title |
| `company` | TEXT | NOT NULL | Employer display name |
| `ats_type` | TEXT | NOT NULL | ATS platform name |
| `ats_id` | TEXT | | Per-ATS identifier |
| `location` | TEXT | | Free-form location |
| `country_iso` | TEXT | | ISO 3166-1 alpha-2 |
| `region` | TEXT | | Continent name |
| `lat` | REAL / DOUBLE PRECISION | | WGS-84 latitude |
| `lon` | REAL / DOUBLE PRECISION | | WGS-84 longitude |
| `is_remote` | INTEGER | | 0/1 or NULL |
| `salary_currency` | TEXT | | ISO 4217 code |
| `salary_period` | TEXT | | HOUR/DAY/WEEK/MONTH/YEAR |
| `salary_summary` | TEXT | | Original salary string |
| `salary_min` | REAL / DOUBLE PRECISION | | Lower bound |
| `salary_max` | REAL / DOUBLE PRECISION | | Upper bound |
| `experience` | INTEGER | | Years |
| `employment_type` | TEXT | | FULL_TIME/PART_TIME/CONTRACT/INTERN/TEMPORARY |
| `department` | TEXT | | Org grouping |
| `team` | TEXT | | Sub-team |
| `requisition_id` | TEXT | | Internal req ID |
| `apply_url` | TEXT | | Direct apply URL |
| `commitment` | TEXT | | Free-form commitment label |
| `description` | TEXT | | Plain-text job description |
| `posted_at` | TEXT | | ISO-8601 UTC |
| `fetched_at` | TEXT | | ISO-8601 UTC |
| `language` | TEXT | | ISO 639-1 code |
| `raw` | TEXT | | ATS-specific overflow JSON blob |

### `companies` — central company directory

| Column | Type | Notes | Indexes |
|---|---|---|---|
| `ats` | TEXT | ATS platform name | `idx_companies_ats` |
| `name` | TEXT | Company display name | |
| `slug` | TEXT | Unique slug (used as URL fallback) | `idx_companies_slug` |
| `url` | TEXT | Company careers URL | |

Unique: `idx_companies_unique (ats, name, slug)`

### `ats` — supported ATS types

| Column | Type | Notes | Index |
|---|---|---|---|
| `ats` | TEXT | ATSType enum value | `idx_ats_unique UNIQUE` (PK in PG) |
| `name` | TEXT | Display name | |
| `slug` | TEXT | Slug | |

### `watchlists` — user-curated company watchlist

| Column | Type | Constraints | Notes |
|---|---|---|---|
| `ats` | TEXT | NOT NULL, part of UNIQUE | ATS platform name |
| `company_name` | TEXT | NOT NULL | |
| `company_slug` | TEXT | NOT NULL, part of UNIQUE | |
| `watchlist` | TEXT | NOT NULL DEFAULT '' | Source file name |
| `created_at` | TEXT / TIMESTAMP | NOT NULL DEFAULT now() | |

### `jobs_recent` — recent job listings (subset of `jobs`)

| Property | Value |
|---|---|
| Columns | Same 29 columns as `jobs` |
| Purpose | Speed up `dump-recent` export |
| Retention | Records within cutoff window (default 24h by `posted_at`) |
| Population | Populated on pipeline flush, pruned/synced on `dump-recent` |

### Per-ATS tables (`{ats_name}`)

| Property | Value |
|---|---|
| Table name | `{ats_name}` (dynamic) |
| Source | `data/parquet/companies_by_ats/{ats}.parquet` |
| Columns | `name` TEXT, `slug` TEXT, `url` TEXT |

### Per-Company tables (`{company_name}`)

| Property | Value |
|---|---|
| Table name | `{company_name}` (dynamic) |
| Columns | TBD |

### Key design notes

| Property | Value |
|---|---|
| Foreign keys | None (fully denormalized) |
| Migrations | None — stale `jobs` schema triggers drop+recreate |
| SQLite tuning | `PRAGMA journal_mode=WAL`, `PRAGMA synchronous=NORMAL` |
| SQLite tuning | `PRAGMA journal_mode=WAL`, `PRAGMA synchronous=NORMAL` |
| Indexes (jobs) | `idx_jobs_company`, `idx_jobs_ats_type`, `idx_jobs_posted_at` |
| Indexes (jobs_recent) | `idx_jobs_recent_posted_at` |
| Indexes (watchlists) | `idx_watchlists_watchlist` |

## Architecture

```
                      Database.initialize()
                            │
                    ┌───────┴───────┐
                    ▼               ▼
           companies.parquet   load_companies_from_parquet()
                    │               │
                    └───────┬───────┘
                            ▼
                     companies table
                            │
                    build_ats_from_companies()
                            │
                            ▼
                      ats table
                    (distinct ats)

                  │ run_producers()
                  ▼
         TokenBucket (10 req/s per ATS)
                  │
       ThreadPoolExecutor (64 workers)
          _fetch_jobs() per company
                  │
         [ Ingest Queue (max 100) ]
                  │
         Worker (daemon thread)
           buffers to batch of 500
                  │
     ┌────────────┼
     ▼            ▼
  SQLite (jobs) Parquet (jobs)

   SIGINT/SIGTERM ⟶ shutdown_event
```


# notes

```
SELECT * FROM "jobs" 
WHERE title LIKE '%software%'
-- AND title LIKE '%us% OR located in the us' 
AND title LIKE '%new grad%' 
-- AND title LIKE '%junior%' 
AND title NOT LIKE '%senior%'
ORDER BY posted_at DESC;
```

```
uv run openats 
uv run openats dump recent jobs
uv run openats collect watchlist 500
uv run openats collect company amazon google microsoft cvs
```