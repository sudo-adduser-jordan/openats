# Plan: Restructure services/ and add services/discover/

## Goal

Reorganize `src/services/` by moving all 47 collectors into `services/collect/` and adding a new `services/discover/` package with company discovery infrastructure.

## 1. Directory Structure (Target)

```
src/services/
├── __init__.py              # re-exports from collect/ + discover/
├── _base.py                 # BaseCollector, CollectorRegistry (unchanged location)
├── _models.py               # ATSType, Job, Company (unchanged location)
├── _helpers.py              # shared utils (unchanged location)
├── _browserbase.py          # browser helpers (unchanged location)
├── _cloakbrowser.py         # stealth browser (unchanged location)
├── collect/                 # ← NEW: all 47 collectors move here
│   ├── __init__.py          # imports all collectors, re-exports
│   ├── amazon.py
│   ├── apple.py
│   ├── ... (47 files)
│   └── ycombinator.py
└── discover/                # ← NEW: company discovery infrastructure
    ├── __init__.py          # re-exports DiscoveryRegistry, BaseDiscovery, etc.
    ├── _base.py             # BaseDiscovery ABC + DiscoveryRegistry
    ├── discover.py          # main orchestrator: runs all registered discoverers
    ├── search.py            # web search-based discovery (Google/Bing site: queries)
    ├── aggregator.py        # job aggregator integration (TheirStack, JobsPipe)
    ├── sitemap.py           # generic sitemap XML/RSS feed parser
    └── jazzhr.py            # ATS-specific: JazzHR sitemap feed discovery
```

## 2. Step-by-Step Changes

### Step 2a: Create `services/collect/` and move collector files

1. Create `src/services/collect/` directory
2. Move all 47 collector `.py` files from `src/services/` into `src/services/collect/`
3. Create `src/services/collect/__init__.py` that imports all collectors (triggers `@register` decorators)
4. Update every collector's internal imports:
   - `from services._base import ...` → stays the same (infrastructure stays in root)
   - `from services._helpers import ...` → stays the same
   - `from services._models import ...` → stays the same
5. No changes needed to `_base.py`, `_models.py`, `_helpers.py`, `_browserbase.py`, `_cloakbrowser.py` — they stay in `src/services/`

**Import impact**: Zero changes to internal collector imports. The `_base`, `_models`, `_helpers` modules stay at `services._base`, etc.

### Step 2b: Update `services/__init__.py`

Change from directly importing 47 collectors to:
```python
from services._base import BaseCollector, CollectorRegistry, get_collector
from services.collect import *  # triggers all @register decorators
```

This preserves backward compatibility for any external code that does `from services import GreenhouseCollector`.

### Step 2c: Update external imports (4 files)

These files import from `services._models` or `services._base` — **no changes needed** since those modules stay in place:
- `src/app.py` line 5: `from services._models import DISABLED_ATS` — **NO CHANGE**
- `src/cli.py` line 15: `from services._models import DISABLED_ATS, ATSType` — **NO CHANGE**
- `src/producer.py` line 8: `from services._base import CollectorRegistry` — **NO CHANGE**
- `src/database/database.py` line 11: `from services._models import ATSType` — **NO CHANGE**

### Step 2d: Update test imports (~38 files)

Tests that import `from services.<collector> import ...` need updating to `from services.collect.<collector> import ...`:
- `from services.ycombinator import ...` → `from services.collect.ycombinator import ...`
- `import services.greenhouse as gh` → `import services.collect.greenhouse as gh`
- `from services._models import ATSType` — **NO CHANGE** (stays in root)
- `from services._base import BaseCollector, CollectorRegistry` — **NO CHANGE** (stays in root)

### Step 2e: Update `pyproject.toml`

```toml
[tool.hatch.build.targets.wheel]
packages = ["src/services"]
```
**NO CHANGE** — hatch auto-discovers subpackages with `__init__.py`.

### Step 2f: Create `services/discover/` package

#### `src/services/discover/__init__.py`
```python
from services.discover._base import BaseDiscovery, DiscoveryRegistry, get_discoverer
```

#### `src/services/discover/_base.py`
- `BaseDiscovery` ABC with:
  - `async def discover(self) -> list[Company]` — abstract method
  - `async def _fetch_with_retry(...)` — shared HTTP helper (mirrors `_base.py` pattern)
- `DiscoveryRegistry` class:
  - `_discoverers: dict[ATSType, type[BaseDiscovery]]`
  - `@DiscoveryRegistry.register(ATSType.X)` decorator
  - `.get(ats)` → `type[BaseDiscovery]`
  - `.all()` → `dict[ATSType, type[BaseDiscovery]]`
- `get_discoverer(ats)` → `BaseDiscovery` instance

#### `src/services/discover/discover.py`
- `discover_companies(ats: ATSType | None = None, write: bool = True) -> list[Company]`
- Orchestrator that:
  1. Iterates `DiscoveryRegistry.all()` (or filters to specific ATS)
  2. Calls `discover()` on each registered discoverer
  3. Deduplicates against existing companies in DB
  4. If `write=True`, inserts new companies into `companies` table
  5. Returns list of newly discovered companies

#### `src/services/discover/search.py`
- `SearchDiscovery(BaseDiscovery)` — generic web search-based discovery
- Uses `httpx` to query Google/Bing with `site:{ats_domain}` queries
- Parses search results to extract company slugs from URLs
- Registered for multiple ATSes: Greenhouse, Lever, Workable, Ashby, SmartRecruiters, Recruitee, BambooHR, Pinpoint, Breezy, Personio, Rippling
- Constructor takes `search_url: str` and `url_pattern: re.Pattern` for per-ATS config

#### `src/services/discover/aggregator.py`
- `AggregatorDiscovery(BaseDiscovery)` — discovers companies via job aggregator sites
- Integrates with TheirStack.com public API (no auth required)
- Paginates through aggregated job listings to extract company-ATS mappings
- Registered for all ATSes as a fallback/supplementary source

#### `src/services/discover/sitemap.py`
- `SitemapDiscovery(BaseDiscovery)` — parses XML sitemaps and RSS feeds
- Generic XML parser for `sitemap.xml` and RSS 2.0 feeds
- Extracts company slugs from URL patterns in `<loc>` and `<link>` elements
- Base class for ATS-specific sitemap discoverers

#### `src/services/discover/jazzhr.py`
- `JazzHRSitemapDiscovery(SitemapDiscovery)` — JazzHR-specific sitemap discovery
- Fetches `app.jazz.co/feeds/google/xml/{0-4}` (5 shards)
- Parses XML to extract company slugs from `{slug}.applytojob.com/apply/{id}/...` URLs
- `@DiscoveryRegistry.register(ATSType.JAZZHR)`
- Highest value discovery source (verified: 5 HTTP requests → thousands of companies)

### Step 2g: Add CLI command for discovery

Add to `src/cli.py`:
```
openats discover [--ats ats_name] [--dry-run]
```

- `--ats`: discover for specific ATS type (default: all registered)
- `--dry-run`: print discovered companies without writing to DB
- Calls `discover_companies()` from `services/discover/discover.py`

## 3. Files Changed Summary

| File | Action |
|------|--------|
| `src/services/collect/__init__.py` | **CREATE** — imports all 47 collectors |
| `src/services/collect/*.py` (47 files) | **MOVE** from `src/services/` (no content changes) |
| `src/services/__init__.py` | **EDIT** — update to re-export from `collect/` |
| `src/services/discover/__init__.py` | **CREATE** — package init |
| `src/services/discover/_base.py` | **CREATE** — BaseDiscovery + DiscoveryRegistry |
| `src/services/discover/discover.py` | **CREATE** — orchestrator |
| `src/services/discover/search.py` | **CREATE** — web search discovery |
| `src/services/discover/aggregator.py` | **CREATE** — aggregator integration |
| `src/services/discover/sitemap.py` | **CREATE** — sitemap parser |
| `src/services/discover/jazzhr.py` | **CREATE** — JazzHR sitemap discovery |
| `src/cli.py` | **EDIT** — add `discover` command |
| `tests/services/test_*.py` (~38 files) | **EDIT** — update `services.<collector>` → `services.collect.<collector>` |

## 4. Import Path Changes

| Pattern | Before | After |
|---------|--------|-------|
| Collector internal | `from services._base import ...` | **NO CHANGE** |
| Collector internal | `from services._models import ...` | **NO CHANGE** |
| External (app.py, cli.py, etc.) | `from services._models import ...` | **NO CHANGE** |
| External (producer.py) | `from services._base import ...` | **NO CHANGE** |
| Test collector import | `from services.<collector> import ...` | `from services.collect.<collector> import ...` |
| Test collector alias | `import services.<collector> as ...` | `import services.collect.<collector> as ...` |

## 5. Verification

1. `ruff check src/` — no lint errors
2. `mypy src/` — no type errors
3. `pytest tests/services/` — all existing tests pass
4. `uv run openats collect greenhouse` — collection still works
5. `uv run openats discover --ats jazzhr --dry-run` — discovery works
