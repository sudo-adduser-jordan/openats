# openats


<!-- Keep these badges in sync with the metadata in pyproject.toml. -->
[![Version 0.1.0](https://img.shields.io/badge/version-0.1.0-brightgreen.svg)](pyproject.toml)
[![Python >=3.11](https://img.shields.io/badge/python-%3E%3D3.11-brightgreen.svg)](pyproject.toml)
[![License: MIT](https://img.shields.io/badge/license-MIT-brightgreen.svg)](pyproject.toml)

## Install

```bash
git clone; uv sync
```

Configuration is optional. To collect from USAJOBS, Wellfound, or the
Browserbase-backed collectors, copy the commented template and fill in keys:

```bash
cp example.env .env
```

# Row

```
global_id, url, title, company, ats_type, ats_id,
location, country_iso, region, is_remote,
salary_currency, salary_period, salary_summary, salary_min, salary_max,
employment_type, department, requisition_id,
description, posted_at, fetched_at, language,
raw
```

## Collectors

**Multi-tenant ATS**:

`Greenhouse`, `Lever`, `Ashby`, `SmartRecruiters`, `Workable`,
`Rippling`, `Personio`, `Gem`, `JoinCom`, `iCIMS`, `JazzHR`, `Breezy`,
`Teamtailor`, `Pinpoint`, `BambooHR`, `Cornerstone`, `Recruitee`,
`Recruiterbox`, `Eightfold`, `Avature`, `Phenom`, `Workday`, `Oracle`,
`SuccessFactors`, `Taleo`, `Mercor`.

**Custom big-tech APIs**: `Amazon`,
`Apple`, `Google`, `TikTok`, `Uber`.

**National public-sector aggregators**: `Bundesagentur` (DE),
`Arbetsformedlingen` (SE), `Eures` (EU/EEA-wide).

**Hybrid jobboards**: `WelcomeToTheJungle`.

**Browser-required** (run via [Browserbase](https://browserbase.com)
remote sessions): `Meta`, `Tesla`. Set `OPENATS_USE_BROWSERBASE=1`
together with `BROWSERBASE_API_KEY` and `BROWSERBASE_PROJECT_ID` to
enable; without those env vars the collectors log a warning and skip.
Tesla also needs a Browserbase project that bypasses Akamai (default
sessions are currently 403'd).

## ATS status

- **Enabled**: registered and not globally disabled. This does not guarantee
  credentials, dependencies, network availability, or matching companies.
- **Disabled**: registered but excluded by `DISABLED_ATS`.
- **Missing**: known type without a registered collector .

<!-- ats-status:start -->
| ATS type | Status |
| --- | --- |
| `amazon` | Enabled |
| `apple` | Enabled |
| `arbetsformedlingen` | Disabled |
| `ashby` | Enabled |
| `avature` | Enabled |
| `bamboohr` | Enabled |
| `breezy` | Enabled |
| `builtin` | Enabled |
| `bundesagentur` | Disabled |
| `cornerstone` | Enabled |
| `custom` | Missing |
| `eightfold` | Enabled |
| `eures` | Disabled |
| `gem` | Enabled |
| `getonbrd` | Enabled |
| `google` | Enabled |
| `greenhouse` | Enabled |
| `icims` | Enabled |
| `infojobs_es` | Enabled |
| `jazzhr` | Enabled |
| `jobs_cz` | Enabled |
| `jobsch` | Enabled |
| `join_com` | Disabled |
| `lever` | Enabled |
| `manfred` | Enabled |
| `mercor` | Enabled |
| `meta` | Enabled |
| `oracle` | Enabled |
| `personio` | Enabled |
| `phenom` | Enabled |
| `pinpoint` | Enabled |
| `programathor` | Enabled |
| `recruitee` | Enabled |
| `recruiterbox` | Enabled |
| `remoteok` | Enabled |
| `rippling` | Enabled |
| `smartrecruiters` | Enabled |
| `successfactors` | Enabled |
| `taleo` | Enabled |
| `teamtailor` | Enabled |
| `tesla` | Enabled |
| `thehub` | Enabled |
| `tiktok` | Enabled |
| `uber` | Enabled |
| `usajobs` | Disabled |
| `wanted` | Enabled |
| `welcometothejungle` | Enabled |
| `wellfound` | Enabled |
| `weworkremotely` | Enabled |
| `workable` | Enabled |
| `workday` | Enabled |
| `ycombinator` | Enabled |
<!-- ats-status:end -->


## Discover

Collectors need a company before they can fetch its jobs. Discovery finds
companies that are not yet in the `companies` table and inserts them:

```bash
openats discover                 # run every registered discoverer, write new rows
openats discover run --ats jazzhr
openats discover --dry-run       # report new companies without writing
openats discover verify          # probe the known sources, live / dead / blocked
openats discover verify -v       # include each source's URL and survey notes
openats discover verify --offline
```

**Only `jazzhr` has a working discoverer.** Finding a tenant slug for a
multi-tenant ATS requires some public index of that ATS's tenants, and after
surveying vendor customer pages, marketing sitemaps, web search, certificate
transparency logs, passive DNS, and job aggregator APIs, exactly one such
index was found: JazzHR's five unauthenticated XML feed shards. Everything
else is dead, blocked, or needs an API key.

`openats discover verify` prints that survey, and
[`src/services/discover/_sources.py`](src/services/discover/_sources.py)
records *why* each source was rejected — read it before adding a discoverer,
so the survey is not re-derived from scratch.

To add a discoverer, see `src/services/discover/_base.py` and register the
module in `src/services/discover/__init__.py`; a module that is not imported
there never reaches `DiscoveryRegistry` and is invisible to `discover`.

## CLI

```bash
openats list-ats
openats collect ashby openai

git clone https://github.com/sudo-adduser-jordan/openats
cd openats
uv sync
pytest
ruff check src/
ruff format src/ --check
```

Collection fetches one company at a time by default — a single process with a
single fetch thread. Pass `--concurrent` (before or after the subcommand) to
fan fetches out over a thread pool instead:

```bash
openats --concurrent
openats collect watchlist ai --concurrent
```