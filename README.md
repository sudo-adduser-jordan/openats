# openats


[![PyPI](https://img.shields.io/pypi/v/openats-py.svg?color=brightgreen)](https://pypi.org/project/openats-py/)
[![Python](https://img.shields.io/pypi/pyversions/openats-py.svg?color=brightgreen)](https://pypi.org/project/openats-py/)
[![License](https://img.shields.io/badge/license-MIT-brightgreen.svg)](LICENSE)

```python
from openats import search

df = search(query="ml engineer", ats="greenhouse", location="Paris")
```

---

## Coverage

| Metric | Value |
|---|---:|
| Live jobs | **3 271 000+** |
| Companies | **86 000+** |
| ATS platforms | **47** |

Top 10 by job count:

| ATS | Jobs |
|---|---:|
| EURES (EU/EEA public-sector) | 1 498 440 |
| Workday | 449 167 |
| SmartRecruiters | 213 154 |
| SuccessFactors | 181 093 |
| Greenhouse | 169 812 |
| Oracle HCM | 144 106 |
| iCIMS | 120 934 |
| JazzHR | 71 050 |
| Lever | 68 303 |
| Phenom | 56 546 |

Counts come from the live manifest at
`https://storage.stapply.ai/openats/v1/manifest.json` — verify any time
with `openats list-ats`.

## Install

```bash
uv install openats-py
```

Distributed as `openats-py` on PyPI; the import name is still `openats`.
`pip install openats` is a different package name and is not used by this
project.

Optional extras:

```bash
pip install "openats-py[parquet]"     # faster downloads via Apache Parquet
pip install "openats-py[collectors]"     # build your own pipeline
pip install "openats-py[all]"
```

## Two ways to use it

### 1. Query the public dataset

```python
from openats import search

# Free-text title + location + remote filter
df = search(query="rust", ats="greenhouse", location="Berlin", remote=True)

# Restrict to one ATS slice (smaller download)
df = search(query="data engineer", ats="ashby")

# Full-dataset search needs the parquet extra because openats/v1/all is
# published as all.parquet.
#   pip install "openats-py[parquet]"
df = search(query="ml engineer", location="Paris")

# Pandas all the way down
df.groupby("company").size().sort_values(ascending=False).head(20)
```

Every row carries:

```
global_id, url, title, company, ats_type, ats_id,
location, country_iso, region, is_remote, lat, lon,
salary_min, salary_max, salary_currency, salary_period, salary_summary,
employment_type, commitment, experience, department, team,
description, posted_at, fetched_at, language,
requisition_id, apply_url, raw
```

Full per-field semantics (types, defaults, derivation rules, examples)
live in [**`SCHEMA.md`**](./SCHEMA.md). `global_id` is the
cross-ATS unique key in the form `{ats_type}:{ats_id}`. Optional fields
are `None` when the source ATS doesn't expose them; `raw` keeps any
provider-specific fields the canonical schema doesn't represent.

### 2. Scrape your own companies

```python
from openats.collectors import GreenhouseCollector, LeverCollector, AshbyCollector

jobs = GreenhouseCollector("anthropic").fetch()    # → list[Job]
jobs = LeverCollector("palantir").fetch()
jobs = AshbyCollector("openai").fetch()
```

Or pick by name:

```python
from openats.collectors import get_collector

collector = get_collector("ashby", "openai")
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
openats search "platform engineer" --location Paris --limit 20
openats collect ashby openai
openats list-ats
```

## Contributing

- **Add a new ATS collector** — every ATS we don't cover yet is a few
  thousand companies missing from the dataset. The collector API is
  intentionally tiny: subclass `BaseCollector`, set `ats`, implement
  `fetch()`. See any file under `src/services/` for a 50-line
  reference, and the `Job` model in `src/services/_models.py` for the
  schema you populate.
- **Improve coverage on an existing ATS** — many collectors extract
  description / salary / employment-type only when the ATS surfaces
  them. If you find a tenant where a field is structurally available
  but we're missing it, a one-line PR is welcome.
- **Add new tenants** — every supported ATS has a CSV under
  [`data/ats/`](./data/ats/). New rows = new companies in
  the dataset. One-line PRs are welcome.
- **Report broken collectors** — open an issue with the slug and the
  failure mode. ATS APIs drift; flagging a regression early keeps the
  dataset accurate for everyone.

```bash
git clone https://github.com/sudo-adduser-jordan/openats
cd openats
uv sync
pytest
ruff check src/
ruff format src/ --check
```

PRs welcome on `main`. CI is green for all 6 of {3.11, 3.12, 3.13} ×
{ubuntu, macos}; please keep it that way.

## License

MIT.

## Acknowledgments

Built with [Reverse API Engineer](https://github.com/kalil0321/reverse-api-engineer).
