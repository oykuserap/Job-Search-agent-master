import logging

import requests

from jobs.ats.base import location_matches, make_dedup_hash, normalize_job_id
from jobs.ats.search_utils import polite_request, search_location, search_terms
from jobs.http_client import get_session

logger = logging.getLogger(__name__)

PAGE_SIZE = 50
MAX_PAGES_PER_TERM = 4


def _parse_slug(slug: str) -> tuple[str, str] | None:
    """Parse '{host}/{siteNumber}', e.g. 'jpmc.fa.oraclecloud.com/CX_1001'."""
    if not slug or "/" not in slug:
        return None
    host, site = (part.strip().strip("/") for part in slug.split("/", 1))
    return (host, site) if host and site else None


def fetch_oracle_hcm_jobs(company: str, slug: str) -> list[dict]:
    parsed = _parse_slug(slug)
    if not parsed:
        logger.warning("Invalid Oracle HCM slug for %s: %s", company, slug)
        return []

    host, site = parsed
    url = f"https://{host}/hcmRestApi/resources/latest/recruitingCEJobRequisitions"
    location = search_location()
    session = get_session()
    jobs: dict[str, dict] = {}

    for term in search_terms():
        for page in range(MAX_PAGES_PER_TERM):
            finder = (
                f'findReqs;siteNumber={site},keyword="{term}",'
                f"limit={PAGE_SIZE},offset={page * PAGE_SIZE},sortBy=POSTING_DATES_DESC"
            )
            params = {
                "onlyData": "true",
                "expand": "requisitionList.secondaryLocations",
                "finder": finder,
            }
            try:
                response = polite_request(session, "GET", url, params=params)
                items = response.json().get("items") or []
            except (requests.RequestException, ValueError) as exc:
                logger.warning("Oracle HCM fetch failed for %s (%s): %s", company, term, exc)
                break

            requisitions = items[0].get("requisitionList", []) if items else []
            for item in requisitions:
                job_ref = str(item.get("Id") or "")
                if not job_ref or job_ref in jobs:
                    continue
                all_locations = [item.get("PrimaryLocation") or ""] + [
                    loc.get("Name", "") for loc in item.get("secondaryLocations") or []
                ]
                if not any(location_matches(loc, location) for loc in all_locations):
                    continue
                title = item.get("Title", "")
                job_location = item.get("PrimaryLocation") or ""
                jobs[job_ref] = {
                    "job_id": normalize_job_id("ohcm", f"{host.split('.')[0]}_{job_ref}"),
                    "title": title,
                    "company": company,
                    "location": job_location,
                    "posted_date": item.get("PostedDate") or "",
                    "job_url": f"https://{host}/hcmUI/CandidateExperience/en/sites/{site}/job/{job_ref}",
                    "source": "oracle_hcm",
                    "source_company": company,
                    "description": item.get("ShortDescriptionStr") or "",
                    "category": item.get("JobFamily", ""),
                    "dedup_hash": make_dedup_hash(company, title, job_location),
                }

            if len(requisitions) < PAGE_SIZE:
                break

    return list(jobs.values())
