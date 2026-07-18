import json
import re
from datetime import datetime

from utils.countries import country_to_region, infer_country_iso, infer_language


def slugify(text: str) -> str:
    s = re.sub(r"[^\w\s-]", "", text.lower())
    return re.sub(r"[-\s]+", "-", s).strip("-")


def _normalize_value(val):
    if isinstance(val, datetime):
        return val.isoformat()
    if isinstance(val, (dict, list)):
        return json.dumps(val) if val else None
    if not isinstance(val, (int, float, bool, str)):
        return str(val) if val is not None else None
    return val


def _enrich_location(job_data: dict) -> None:
    if not job_data.get("country_iso"):
        job_data["country_iso"] = infer_country_iso(job_data.get("location"))
    if not job_data.get("region"):
        job_data["region"] = country_to_region(job_data.get("country_iso"))


def _enrich_language(job_data: dict) -> None:
    if not job_data.get("language"):
        job_data["language"] = infer_language(job_data.get("country_iso"))


def normalize_jobs(jobs) -> list[dict]:
    processed = []
    for job in jobs:
        if hasattr(job, "model_dump"):
            job_data = job.model_dump()
        elif hasattr(job, "__dict__"):
            job_data = {k: v for k, v in vars(job).items() if not k.startswith("__")}
        else:
            job_data = job
        _enrich_location(job_data)
        _enrich_language(job_data)
        processed.append({k: _normalize_value(v) for k, v in job_data.items()})
    return processed
