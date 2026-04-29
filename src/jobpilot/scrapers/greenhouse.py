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

from .base import BaseScraper, RawJob

logger = logging.getLogger(__name__)

GREENHOUSE_API = "https://boards-api.greenhouse.io/v1/boards"

_http_retry = retry(
    stop=stop_after_attempt(3),
    wait=wait_exponential(multiplier=1, min=2, max=10),
    retry=retry_if_exception_type((httpx.HTTPError, httpx.TimeoutException)),
    reraise=True,
)


def _slugify(title: str) -> str:
    slug = title.lower()
    slug = re.sub(r"[^a-z0-9\s-]", "", slug)
    slug = re.sub(r"\s+", "-", slug).strip("-")
    slug = re.sub(r"-+", "-", slug)
    return slug


class GreenhouseScraper(BaseScraper):
    def __init__(
        self, board_slug: str, company_name: str, url_template: str | None = None
    ):
        self.board_slug = board_slug
        self.company_name = company_name
        self.url_template = url_template

    def fetch_jobs(self) -> list[RawJob]:
        url = f"{GREENHOUSE_API}/{self.board_slug}/jobs?content=true"
        try:
            resp = self._fetch_with_retry(url)
            return self._parse_response(resp.json())
        except Exception as e:
            logger.error(f"Failed to fetch {self.company_name} jobs: {e}")
            return []

    @_http_retry
    def _fetch_with_retry(self, url: str) -> httpx.Response:
        resp = httpx.get(url, timeout=30, headers={"User-Agent": "JobPilot/1.0"})
        resp.raise_for_status()
        return resp

    def _parse_response(self, data: dict) -> list[RawJob]:
        jobs = []
        now = datetime.now(timezone.utc)
        for item in data.get("jobs", []):
            salary = self._extract_salary(item.get("content", ""))
            seniority = self._extract_metadata(item, "IC or MG")
            jobs.append(
                RawJob(
                    external_id=str(item["id"]),
                    company=self.company_name,
                    title=item["title"],
                    url=self._build_url(item),
                    location=item.get("location", {}).get("name"),
                    remote=self._is_remote(item),
                    salary=salary,
                    description=item.get("content"),
                    department=(item.get("departments") or [{}])[0].get("name")
                    if item.get("departments")
                    else None,
                    seniority=seniority,
                    scraped_at=now,
                )
            )
        return jobs

    def _build_url(self, item: dict) -> str:
        if self.url_template:
            slug = _slugify(item.get("title", ""))
            return self.url_template.format(slug=slug, id=item["id"])
        return f"https://job-boards.greenhouse.io/{self.board_slug}/jobs/{item['id']}"

    def _extract_salary(self, html_content: str) -> str | None:
        patterns = [
            r"\$[\d,]+\s*[-–]\s*\$[\d,]+",
            r"\$[\d,]+(?:\.\d{2})?(?:\s*(?:to|[-–])\s*\$[\d,]+(?:\.\d{2})?)?",
        ]
        for pattern in patterns:
            match = re.search(pattern, html_content)
            if match:
                return match.group(0)
        return None

    def _is_remote(self, item: dict) -> bool | None:
        location = item.get("location", {}).get("name", "")
        if location and "remote" in location.lower():
            return True
        return None

    def is_job_live(self, url: str) -> bool | None:
        try:
            resp = httpx.get(url, timeout=10, follow_redirects=True)
            if resp.status_code in (404, 410):
                return False
            if resp.status_code == 200:
                return True
            return None
        except Exception:
            return None

    def _extract_metadata(self, item: dict, field_name: str) -> str | None:
        for meta in item.get("metadata") or []:
            if meta.get("name") == field_name:
                return meta.get("value")
        return None
