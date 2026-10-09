import logging

import requests

from jobs.ats.base import make_dedup_hash, normalize_job_id
from jobs.ats.search_utils import iso_from_timestamp, polite_request, search_location, search_terms
from jobs.http_client import get_session

logger = logging.getLogger(__name__)

SEARCH_URL = "https://apply.careers.microsoft.com/api/pcsx/search"
JOB_URL = "https://apply.careers.microsoft.com/careers/job/{id}"
PAGE_SIZE = 10  # fixed by the API
MAX_PAGES_PER_TERM = 10


def fetch_microsoft_jobs(company: str, slug: str = "") -> list[dict]:
    location = search_location()
    session = get_session()
    jobs: dict[str, dict] = {}

    for term in search_terms():
        for page in range(MAX_PAGES_PER_TERM):
            params = {
                "domain": "microsoft.com",
                "query": term,
                "location": location,
                "start": page * PAGE_SIZE,
                "sort_by": "timestamp",
            }
            try:
                response = polite_request(session, "GET", SEARCH_URL, params=params)
                positions = (response.json().get("data") or {}).get("positions") or []
            except (requests.RequestException, ValueError) as exc:
                logger.warning("Microsoft fetch failed for %s (%s): %s", company, term, exc)
                break

            for item in positions:
                job_ref = str(item.get("displayJobId") or item.get("id") or "")
                if not job_ref or job_ref in jobs:
                    continue
                title = item.get("name", "")
                job_location = "; ".join(item.get("standardizedLocations") or item.get("locations") or [])
                jobs[job_ref] = {
                    "job_id": normalize_job_id("msft", job_ref),
                    "title": title,
                    "company": company,
                    "location": job_location,
                    "posted_date": iso_from_timestamp(item.get("postedTs")),
                    "job_url": JOB_URL.format(id=item.get("id")),
                    "source": "microsoft",
                    "source_company": company,
                    "category": item.get("department", ""),
                    "dedup_hash": make_dedup_hash(company, title, job_location),
                }

            if len(positions) < PAGE_SIZE:
                break

    return list(jobs.values())
