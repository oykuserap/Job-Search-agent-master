import json
import logging
import re

import requests

from jobs.ats.base import make_dedup_hash, normalize_job_id
from jobs.ats.search_utils import iso_from_timestamp, polite_request, search_location, search_terms
from jobs.http_client import get_session

logger = logging.getLogger(__name__)

# Google's careers site has no public JSON API; results are embedded in the page.
SEARCH_URL = "https://www.google.com/about/careers/applications/jobs/results/"
JOB_URL = "https://www.google.com/about/careers/applications/jobs/results/{id}"
MAX_PAGES_PER_TERM = 5
_DATA_RE = re.compile(r"AF_initDataCallback\(\{key: 'ds:1'.*?data:(.*?), sideChannel", re.S)


def _field(item: list, index: int):
    return item[index] if len(item) > index else None


def _html_field(item: list, index: int) -> str:
    value = _field(item, index)
    if isinstance(value, list) and len(value) > 1 and isinstance(value[1], str):
        return value[1]
    return ""


def _parse_page(html: str) -> list[list]:
    match = _DATA_RE.search(html)
    if not match:
        return []
    try:
        data = json.loads(match.group(1))
    except ValueError:
        return []
    return data[0] if data and isinstance(data[0], list) else []


def fetch_google_jobs(company: str, slug: str = "") -> list[dict]:
    location = search_location()
    session = get_session()
    jobs: dict[str, dict] = {}

    for term in search_terms():
        for page in range(1, MAX_PAGES_PER_TERM + 1):
            params = {"q": term, "location": location, "sort_by": "date", "page": page}
            try:
                response = polite_request(session, "GET", SEARCH_URL, params=params)
            except requests.RequestException as exc:
                logger.warning("Google fetch failed for %s (%s): %s", company, term, exc)
                break

            items = _parse_page(response.text)
            if not items:
                if page == 1:
                    logger.warning("Google careers page format changed; no jobs parsed for '%s'", term)
                break

            for item in items:
                job_ref = str(_field(item, 0) or "")
                if not job_ref or job_ref in jobs:
                    continue
                title = _field(item, 1) or ""
                locations = _field(item, 9) or []
                job_location = "; ".join(loc[0] for loc in locations if loc and loc[0])
                created = _field(item, 12)
                description = " ".join(
                    filter(None, (_html_field(item, 10), _html_field(item, 3), _html_field(item, 4)))
                )
                jobs[job_ref] = {
                    "job_id": normalize_job_id("goog", job_ref),
                    "title": title,
                    "company": company,
                    "location": job_location,
                    "posted_date": iso_from_timestamp(created[0]) if created else "",
                    "job_url": JOB_URL.format(id=job_ref),
                    "source": "google",
                    "source_company": company,
                    "description": description,
                    "dedup_hash": make_dedup_hash(company, title, job_location),
                }

    return list(jobs.values())
