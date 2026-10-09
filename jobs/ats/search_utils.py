"""Shared helpers for company career sites that expose a search API (not a full board)."""

import logging
import time
from datetime import datetime, timezone

from config import USER_PROFILE

logger = logging.getLogger(__name__)

MAX_SEARCH_TERMS = 4


def search_terms() -> list[str]:
    """Role keywords to search for; falls back to a generic engineering query."""
    roles = [r for r in USER_PROFILE.get("target_roles", []) if r.strip()]
    return roles[:MAX_SEARCH_TERMS] or ["Software Engineer"]


def search_location() -> str:
    return USER_PROFILE.get("location", "").strip()


def iso_from_timestamp(seconds) -> str:
    try:
        return datetime.fromtimestamp(float(seconds), tz=timezone.utc).strftime("%Y-%m-%d")
    except (TypeError, ValueError, OverflowError, OSError):
        return ""


PAGE_DELAY_SECONDS = 1.0
MAX_RETRIES = 3


def polite_request(session, method: str, url: str, **kwargs):
    """Send a request with a short delay and back off on HTTP 429/503 rate limits."""
    kwargs.setdefault("timeout", 20)
    for attempt in range(MAX_RETRIES + 1):
        time.sleep(PAGE_DELAY_SECONDS)
        response = session.request(method, url, **kwargs)
        if response.status_code not in (429, 503) or attempt == MAX_RETRIES:
            response.raise_for_status()
            return response
        retry_after = response.headers.get("Retry-After", "")
        wait = int(retry_after) if retry_after.isdigit() else 5 * (2 ** attempt)
        logger.info("Rate limited by %s; retrying in %ds", url.split("/")[2], wait)
        time.sleep(min(wait, 60))
    return response
