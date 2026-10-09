import logging
from concurrent.futures import ThreadPoolExecutor, as_completed

from config import FETCH_CONCURRENCY, USER_PROFILE
from jobs.ats.amazon import fetch_amazon_jobs
from jobs.ats.ashby import fetch_ashby_jobs
from jobs.ats.goldman import fetch_goldman_jobs
from jobs.ats.google import fetch_google_jobs
from jobs.ats.greenhouse import fetch_greenhouse_jobs
from jobs.ats.lever import fetch_lever_jobs
from jobs.ats.microsoft import fetch_microsoft_jobs
from jobs.ats.oracle_hcm import fetch_oracle_hcm_jobs
from jobs.ats.smartrecruiters import fetch_smartrecruiters_jobs
from jobs.ats.workday import fetch_workday_jobs
from jobs.career_discovery import discover_ats
from jobs.career_registry import ALL_COMPANIES, get_career_config
from jobs.company_utils import role_matches
from jobs.database import get_cached_ats, set_cached_ats
from jobs.profile_filter import profile_matches

logger = logging.getLogger(__name__)

ATS_FETCHERS = {
    "greenhouse": fetch_greenhouse_jobs,
    "lever": fetch_lever_jobs,
    "ashby": fetch_ashby_jobs,
    "smartrecruiters": fetch_smartrecruiters_jobs,
    "workday": fetch_workday_jobs,
    "oracle_hcm": fetch_oracle_hcm_jobs,
    "amazon": fetch_amazon_jobs,
    "google": fetch_google_jobs,
    "microsoft": fetch_microsoft_jobs,
    "goldman": fetch_goldman_jobs,
}


def _fetch_from_ats(company: str, ats: str, slug: str) -> list[dict]:
    fetcher = ATS_FETCHERS.get(ats)
    if not fetcher:
        return []

    location = USER_PROFILE.get("location", "")
    if ats == "smartrecruiters":
        return fetcher(company, slug, location_filter=location)
    return fetcher(company, slug)


def fetch_career_jobs_for_company(company: str) -> list[dict]:
    config = get_career_config(company)
    ats = config.get("ats")
    slug = config.get("slug")

    if not ats or not slug:
        cached = get_cached_ats(company)
        if cached:
            ats = cached["ats"]
            slug = cached["slug"]
        else:
            career_url = config.get("career_url", "")
            discovered = discover_ats(career_url)
            if discovered:
                ats = discovered["ats"]
                slug = discovered["slug"]
                set_cached_ats(company, ats, slug)
            else:
                logger.info(
                    "No career-site API for %s; only LinkedIn results will be used", company
                )
                return []

    jobs = _fetch_from_ats(company, ats, slug)

    if USER_PROFILE.get("filter_by_role", True):
        roles = USER_PROFILE.get("target_roles", [])
        # "category" (job family) helps sites with non-descriptive titles, e.g.
        # Goldman's "Market Risk Analytics, Associate" under "Software Engineering".
        jobs = [
            j for j in jobs
            if role_matches(f"{j.get('title', '')} {j.get('category', '')}", roles)
        ]

    jobs = [j for j in jobs if profile_matches(j)]

    logger.info("Career site: %d jobs from %s (%s/%s)", len(jobs), company, ats, slug)
    return jobs


def fetch_all_career_jobs() -> list[dict]:
    companies = USER_PROFILE.get("target_companies") or ALL_COMPANIES
    all_jobs: list[dict] = []
    seen_ids: set[str] = set()
    seen_dedup: set[str] = set()
    workers = min(FETCH_CONCURRENCY, max(1, len(companies)))

    with ThreadPoolExecutor(max_workers=workers) as executor:
        futures = {
            executor.submit(fetch_career_jobs_for_company, company): company
            for company in companies
        }
        for future in as_completed(futures):
            company = futures[future]
            try:
                company_jobs = future.result()
            except Exception:
                logger.exception("Career fetch failed for %s", company)
                continue

            for job in company_jobs:
                job_id = job.get("job_id")
                dedup = job.get("dedup_hash", "")

                if job_id in seen_ids:
                    continue
                if dedup and dedup in seen_dedup:
                    continue

                seen_ids.add(job_id)
                if dedup:
                    seen_dedup.add(dedup)
                all_jobs.append(job)

    logger.info("Total career site jobs: %d", len(all_jobs))
    return all_jobs
