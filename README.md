# openats


[![PyPI](https://img.shields.io/pypi/v/openats-py.svg?color=brightgreen)](https://pypi.org/project/openats-py/)
[![Python](https://img.shields.io/pypi/pyversions/openats-py.svg?color=brightgreen)](https://pypi.org/project/openats-py/)
[![License](https://img.shields.io/badge/license-MIT-brightgreen.svg)](LICENSE)

## Install

```bash
git clone; uv sync
```

# Row

```
global_id, url, title, company, ats_type, ats_id,
location, country_iso, region, is_remote, lat, lon,
salary_min, salary_max, salary_currency, salary_period, salary_summary,
employment_type, commitment, experience, department, team,
description, posted_at, fetched_at, language,
requisition_id, apply_url, raw
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
remote sessions): `Meta`, `Tesla`. Set `JOBHIVE_USE_BROWSERBASE=1`
together with `BROWSERBASE_API_KEY` and `BROWSERBASE_PROJECT_ID` to
enable; without those env vars the collectors log a warning and skip.
Tesla also needs a Browserbase project that bypasses Akamai (default
sessions are currently 403'd).

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