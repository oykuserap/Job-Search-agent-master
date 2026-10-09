import logging

import requests

from jobs.ats.base import location_matches, make_dedup_hash, normalize_job_id
from jobs.ats.search_utils import polite_request, search_location, search_terms
from jobs.http_client import get_session

logger = logging.getLogger(__name__)

GRAPHQL_URL = "https://api-higher.gs.com/gateway/api/v1/graphql"
JOB_URL = "https://higher.gs.com/roles/{id}"
PAGE_SIZE = 100
MAX_PAGES_PER_TERM = 3
QUERY = """
query GetRoles($searchQueryInput: RoleSearchQueryInput!) {
  roleSearch(searchQueryInput: $searchQueryInput) {
    totalCount
    items {
      roleId corporateTitle jobTitle jobFunction division
      lastPostedDate descriptionHtml
      locations { primary city state country }
      externalSource { sourceId }
    }
  }
}
"""


def _format_location(loc: dict) -> str:
    return ", ".join(part for part in (loc.get("city"), loc.get("state"), loc.get("country")) if part)


def fetch_goldman_jobs(company: str, slug: str = "") -> list[dict]:
    location = search_location()
    session = get_session()
    jobs: dict[str, dict] = {}

    for term in search_terms():
        for page in range(MAX_PAGES_PER_TERM):
            variables = {
                "searchQueryInput": {
                    "page": {"pageSize": PAGE_SIZE, "pageNumber": page},
                    "sort": {"sortStrategy": "POSTED_DATE", "sortOrder": "DESC"},
                    "filters": [],
                    "experiences": ["EARLY_CAREER", "PROFESSIONAL"],
                    "searchTerm": term,
                }
            }
            try:
                response = polite_request(
                    session,
                    "POST",
                    GRAPHQL_URL,
                    json={"operationName": "GetRoles", "query": QUERY, "variables": variables},
                )
                result = (response.json().get("data") or {}).get("roleSearch") or {}
            except (requests.RequestException, ValueError) as exc:
                logger.warning("Goldman Sachs fetch failed for %s (%s): %s", company, term, exc)
                break

            items = result.get("items") or []
            for item in items:
                source_id = (item.get("externalSource") or {}).get("sourceId") or ""
                job_ref = source_id or item.get("roleId") or ""
                if not job_ref or job_ref in jobs:
                    continue
                locations = [_format_location(loc) for loc in item.get("locations") or []]
                if not any(location_matches(loc, location) for loc in locations or [""]):
                    continue
                title = item.get("jobTitle", "")
                job_location = "; ".join(loc for loc in locations if loc)
                jobs[job_ref] = {
                    "job_id": normalize_job_id("gs", job_ref),
                    "title": title,
                    "company": company,
                    "location": job_location,
                    "posted_date": (item.get("lastPostedDate") or "")[:10],
                    "job_url": JOB_URL.format(id=job_ref),
                    "source": "goldman",
                    "source_company": company,
                    "description": item.get("descriptionHtml") or "",
                    "category": item.get("jobFunction", ""),
                    "dedup_hash": make_dedup_hash(company, title, job_location),
                }

            if len(items) < PAGE_SIZE:
                break

    return list(jobs.values())
