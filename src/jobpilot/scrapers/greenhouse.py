import logging
import re
from datetime import datetime, timezone

import httpx
from tenacity import (
    retry,
    retry_if_exception_type,
    stop_after_attempt,
    wait_exponential,
)

from jobpilot.fetch_description import html_to_text
from jobpilot.scrapers.base import BaseScraper, RawJob

logger = logging.getLogger(__name__)

GREENHOUSE_API = "https://boards-api.greenhouse.io/v1/boards"

_http_retry = retry(
    stop=stop_after_attempt(3),
    wait=wait_exponential(multiplier=1, min=2, max=10),
    retry=retry_if_exception_type((httpx.HTTPError, httpx.TimeoutException)),
    reraise=True,
)


def _slugify(name: str) -> str:
    slug = name.lower()
    slug = re.sub(r"[^a-z0-9\s-]", "", slug)
    slug = re.sub(r"\s+", "-", slug).strip("-")
    return re.sub(r"-+", "-", slug)


def probe_greenhouse(company_name: str) -> "GreenhouseScraper | None":
    """Try the slugified company name against the Greenhouse API.

    Returns a GreenhouseScraper if the board exists, None otherwise.
    Fails silently — absence means the company isn't on Greenhouse or uses
    a non-standard slug.
    """
    slug = _slugify(company_name)
    url = f"{GREENHOUSE_API}/{slug}/jobs"
    try:
        resp = httpx.get(url, timeout=5, headers={"User-Agent": "jobPilot/1.0"})
        if resp.status_code == 200 and resp.json().get("jobs") is not None:
            logger.info(f"Greenhouse board found: {company_name!r} (slug={slug!r})")
            return GreenhouseScraper(board_slug=slug, company_name=company_name)
    except Exception as exc:
        logger.debug(f"Greenhouse probe failed for {company_name!r}: {exc}")
    return None


class GreenhouseScraper(BaseScraper):
    source = "greenhouse"
    tracks_full_company_listing = True

    def __init__(self, board_slug: str, company_name: str):
        self.board_slug = board_slug
        self.company_name = company_name

    def fetch_jobs(self) -> list[RawJob]:
        url = f"{GREENHOUSE_API}/{self.board_slug}/jobs?content=true"
        try:
            resp = self._fetch_with_retry(url)
            return self._parse_response(resp.json())
        except Exception as exc:
            logger.error(f"Greenhouse fetch failed for {self.company_name!r}: {exc}")
            return []

    @_http_retry
    def _fetch_with_retry(self, url: str) -> httpx.Response:
        resp = httpx.get(url, timeout=30, headers={"User-Agent": "jobPilot/1.0"})
        resp.raise_for_status()
        return resp

    def _parse_response(self, data: dict) -> list[RawJob]:
        now = datetime.now(timezone.utc)
        jobs = []
        for item in data.get("jobs", []):
            jobs.append(
                RawJob(
                    external_id=str(item["id"]),
                    company=self.company_name,
                    title=item["title"],
                    url=f"https://job-boards.greenhouse.io/{self.board_slug}/jobs/{item['id']}",
                    location=(item.get("location") or {}).get("name"),
                    remote=self._is_remote(item),
                    salary=self._extract_salary(item.get("content") or ""),
                    description=html_to_text(item["content"]) if item.get("content") else None,
                    department=((item.get("departments") or [{}])[0].get("name")),
                    seniority=None,
                    scraped_at=now,
                )
            )
        return jobs

    def _is_remote(self, item: dict) -> bool | None:
        loc = (item.get("location") or {}).get("name", "")
        return True if "remote" in loc.lower() else None

    def _extract_salary(self, html: str) -> str | None:
        for pattern in [
            r"\$[\d,]+\s*[-–]\s*\$[\d,]+",
            r"\$[\d,]+(?:\.\d{2})?(?:\s*(?:to|[-–])\s*\$[\d,]+(?:\.\d{2})?)?",
        ]:
            m = re.search(pattern, html)
            if m:
                return m.group(0)
        return None
