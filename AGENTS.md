## Commands

### Setup and checks

- `uv sync --extra dev` — Install runtime and development dependencies (Python 3.11+).
- `uv run ruff check src/` — Lint source code.
- `uv run mypy src/` — Check types.
- `uv run ruff format src/` — Format source code; add `--check` to verify without editing.
- `uv run pylint src/` — Run additional lint checks.
- `uv run pytest` — Run tests.

Run the CLI commands below with `uv run openats` in place of `openats` when using uv.
Square brackets indicate optional arguments; angle brackets indicate required values.

### Database

- `openats database` — Create or reinitialize the database schema.
- `openats load database` — Load company and watchlist seed data from Parquet.

### Collect

- `openats` — Run the full collection pipeline.
- `openats collect [--skip <ats> ...]` — Collect all companies, optionally skipping ATS types.
- `openats collect company <company> ...` — Collect specified company names or slugs.
- `openats collect ats <ats> ... [--skip <slug> ...]` — Collect specified ATS types, optionally skipping company slugs.
- `openats collect watchlist [watchlist] [--skip-ats <ats> ...]` — Collect one watchlist or all watchlists.

### Dump

Outputs are under `data/parquet/`.

- `openats dump recent jobs` — Export jobs posted in the last 24 hours to `jobs_recent.parquet`.
- `openats dump ats [ats ...]` — Export jobs by ATS to `jobs_by_ats/` (default: all).
- `openats dump company [companies ...]` — Export jobs by company to `jobs_by_company/` (default: all).
- `openats dump companies-table` — Export the company directory to `companies.parquet`.
- `openats dump watchlist-table` — Export watchlist entries to `watchlists.parquet`.
- `openats dump watchlist [watchlist]` — Export watchlist jobs to `jobs_by_watchlist/` (default: all).

### Watchlist

- `openats watchlist load <path>` — Load watchlists from a directory of Parquet files.
- `openats watchlist list` — List available watchlist titles.
- `openats remove unwatched [--dry-run]` — Remove companies outside all watchlists; dry-run reports only.

### Validate

- `openats validate jobs [--workers N] [--dry-run]` — Remove jobs whose URLs return 404/410; dry-run reports only.
- `openats validate companies [--workers N] [--dry-run]` — Remove companies whose URLs return 404/410; dry-run reports only.

## File structure and locations

- `src/` — Python application source.
- `src/cli.py` — CLI commands and argument definitions.
- `src/app.py`, `src/producer.py`, `src/workers.py` — Pipeline entry point, collection scheduling, and ingestion.
- `src/config.py` — Database path and concurrency settings.
- `src/database/` — Database schema, persistence, and Parquet import/export.
- `src/services/collect/` — ATS-specific job collectors.
- `src/services/discover/` — Company discovery services.
- `src/services/_models.py` — Shared job models; `src/utils/` holds normalization and other helpers.
- `tests/` — Pytest suite and fixtures.
- `data/database.db` — Local SQLite database, created at runtime; path configured in `src/config.py`.
- `data/parquet/` — Seed data and exports; `data/parquet/watchlists/` holds watchlist inputs.
- `data/search.sql` — Example job search queries.
- `pyproject.toml`, `uv.lock` — Package metadata, dependencies, tool settings, and dependency lockfile.
- `.github/workflows/` — GitHub Actions workflows.

## Documentation links

- [Installation](README.md#install), [job row fields](README.md#row), [collectors](README.md#collectors), and [CLI overview](README.md#cli).
- [CLI source](src/cli.py) — Authoritative commands and options.
- [Database source](src/database/database.py) and [job models](src/services/_models.py) — Schema and persistence reference.
- [Pipeline entry point](src/app.py), [producer](src/producer.py), and [worker](src/workers.py) — Collection and ingestion implementation.
- [Project configuration](pyproject.toml) — Dependencies and development tooling.

No `docs/` directory currently exists; use the README and source references above.
