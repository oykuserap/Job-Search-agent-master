import logging
import re
from datetime import datetime

import requests

from jobs.ats.base import location_matches, make_dedup_hash, normalize_job_id
from jobs.ats.search_utils import polite_request, search_location, search_terms
from jobs.http_client import get_session

logger = logging.getLogger(__name__)

SEARCH_URL = "https://www.amazon.jobs/en/search.json"
PAGE_SIZE = 100
MAX_PAGES_PER_TERM = 2


def _iso_date(value: str) -> str:
    text = re.sub(r"\s+", " ", value or "").strip()
    try:
        return datetime.strptime(text, "%B %d, %Y").strftime("%Y-%m-%d")
    except ValueError:
        return text


def fetch_amazon_jobs(company: str, slug: str = "") -> list[dict]:
    location = search_location()
    session = get_session()
    jobs: dict[str, dict] = {}

    for term in search_terms():
        for page in range(MAX_PAGES_PER_TERM):
            params = {
                "base_query": term,
                "loc_query": location,
                "result_limit": PAGE_SIZE,
                "offset": page * PAGE_SIZE,
                "sort": "recent",
            }
            try:
                response = polite_request(session, "GET", SEARCH_URL, params=params)
                data = response.json()
            except (requests.RequestException, ValueError) as exc:
                logger.warning("Amazon fetch failed for %s (%s): %s", company, term, exc)
                break

            postings = data.get("jobs") or []
            for item in postings:
                job_ref = item.get("id_icims") or item.get("id")
                job_location = item.get("normalized_location") or item.get("location", "")
                if not job_ref or job_ref in jobs or not location_matches(job_location, location):
                    continue
                title = item.get("title", "")
                description = " ".join(
                    part for part in (
                        item.get("description", ""),
                        item.get("basic_qualifications", ""),
                        item.get("preferred_qualifications", ""),
                    ) if part
                )
                jobs[job_ref] = {
                    "job_id": normalize_job_id("amzn", job_ref),
                    "title": title,
                    "company": company,
                    "location": job_location,
                    "posted_date": _iso_date(item.get("posted_date", "")),
                    "job_url": f"https://www.amazon.jobs{item.get('job_path', '')}",
                    "source": "amazon",
                    "source_company": company,
                    "description": description,
                    "category": item.get("job_family", ""),
                    "dedup_hash": make_dedup_hash(company, title, job_location),
                }

            if len(postings) < PAGE_SIZE:
                break

    return list(jobs.values())
