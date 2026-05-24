import logging
import re
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone

import httpx
from tenacity import (
    retry,
    retry_if_exception_type,
    stop_after_attempt,
    wait_exponential,
)

from jobpilot.scrapers.base import BaseScraper, RawJob

logger = logging.getLogger(__name__)

_MAX_JOBS = 500
_PAGE_SIZE = 20

_http_retry = retry(
    stop=stop_after_attempt(3),
    wait=wait_exponential(multiplier=1, min=2, max=10),
    retry=retry_if_exception_type((httpx.HTTPError, httpx.TimeoutException)),
    reraise=True,
)


def _slugify(name: str) -> str:
    slug = name.lower().strip()
    slug = re.sub(r"[^a-z0-9\s-]", "", slug)
    slug = re.sub(r"\s+", "", slug)
    return slug


class WorkdayProbeError(Exception):
    """Server-side issue (5xx, timeout, connection) — distinct from a 404."""


def _try_workday_combo(company_slug: str, instance: int, site: str) -> str | None:
    """Try a single Workday URL combo. Returns the base URL on success, None on 404."""
    base_url = f"https://{company_slug}.wd{instance}.myworkdayjobs.com"
    jobs_url = f"{base_url}/wday/cxs/{company_slug}/{site}/jobs"
    try:
        resp = httpx.post(
            jobs_url,
            json={"limit": 1, "offset": 0, "searchText": ""},
            headers={"Content-Type": "application/json", "User-Agent": "jobPilot/1.0"},
            timeout=5,
        )
    except (httpx.TimeoutException, httpx.HTTPError):
        return None

    if resp.status_code == 200:
        try:
            data = resp.json()
        except ValueError:
            return None
        if "jobPostings" in data:
            return jobs_url
    return None


def probe_workday(company_name: str) -> "WorkdayScraper | None":
    """Best-effort probe across Workday instance/site combinations.

    Fans out all combos in parallel via ThreadPoolExecutor, returns on
    the first 200 hit. Returns None if all combos 404. Raises
    WorkdayProbeError only if transient network errors dominate.
    """
    company_slug = _slugify(company_name)
    if not company_slug:
        return None

    instances = [1, 3, 5, 2, 4]
    sites = [
        company_slug,
        "External",
        "Careers",
        f"{company_slug}_Careers",
        f"en-US/{company_slug}",
    ]

    combos = [(company_slug, inst, site) for inst in instances for site in sites]
    found_url: str | None = None

    with ThreadPoolExecutor(max_workers=10) as executor:
        futures = {
            executor.submit(_try_workday_combo, slug, inst, site): (slug, inst, site)
            for slug, inst, site in combos
        }
        for future in as_completed(futures, timeout=10):
            try:
                result = future.result()
            except Exception:
                continue
            if result is not None:
                found_url = result
                # Cancel remaining futures
                for f in futures:
                    f.cancel()
                break

    if found_url:
        logger.info("Workday board found: %r at %s", company_name, found_url)
        return WorkdayScraper(
            jobs_url=found_url,
            company_name=company_name,
            company_slug=company_slug,
        )

    logger.debug("Workday board not found for %r", company_name)
    return None


class WorkdayScraper(BaseScraper):
    source = "workday"
    tracks_full_company_listing = True

    def __init__(self, jobs_url: str, company_name: str, company_slug: str):
        self.jobs_url = jobs_url
        self.company_name = company_name
        self.company_slug = company_slug
        # Derive the base URL for constructing job links
        # jobs_url looks like: https://foo.wd5.myworkdayjobs.com/wday/cxs/foo/Site/jobs
        # base for links: https://foo.wd5.myworkdayjobs.com
        match = re.match(r"(https://[^/]+)", jobs_url)
        self.base_url = match.group(1) if match else ""

    def fetch_jobs(self) -> list[RawJob]:
        try:
            return self._paginate()
        except Exception as exc:
            logger.error(f"Workday fetch failed for {self.company_name!r}: {exc}")
            return []

    def _paginate(self) -> list[RawJob]:
        now = datetime.now(timezone.utc)
        all_jobs: list[RawJob] = []
        offset = 0

        while offset < _MAX_JOBS:
            resp = self._fetch_page(offset)
            data = resp.json()
            postings = data.get("jobPostings") or []
            total = data.get("total", 0)

            for item in postings:
                all_jobs.append(self._parse_posting(item, now))

            offset += _PAGE_SIZE
            if not postings or offset >= total or offset >= _MAX_JOBS:
                break

        return all_jobs

    @_http_retry
    def _fetch_page(self, offset: int) -> httpx.Response:
        resp = httpx.post(
            self.jobs_url,
            json={"limit": _PAGE_SIZE, "offset": offset, "searchText": ""},
            headers={"Content-Type": "application/json", "User-Agent": "jobPilot/1.0"},
            timeout=30,
        )
        resp.raise_for_status()
        return resp

    def _parse_posting(self, item: dict, now: datetime) -> RawJob:
        title = item.get("title") or "Untitled"
        external_path = item.get("externalPath") or ""
        url = f"{self.base_url}{external_path}" if external_path else ""
        locations_text = item.get("locationsText") or None
        bullet_fields = item.get("bulletFields") or []

        # bulletFields often contains: job ID, department, time type (Full time, etc.)
        department = None
        external_id = ""
        for field in bullet_fields:
            if not field:
                continue
            if re.match(r"^[A-Z]{1,5}\d+|^JR\d+|^\d{6,}", field):
                external_id = field
            elif not department and not re.match(r"^(Full|Part)\s*(Time|time)", field):
                department = field

        if not external_id:
            # Fallback: extract from externalPath
            external_id = external_path.rsplit("/", 1)[-1] if external_path else title

        # Description: not fetched per-job to avoid runaway requests.
        # The lazy fetch_full_description fetcher handles this on demand.
        description = None

        return RawJob(
            external_id=external_id,
            company=self.company_name,
            title=title,
            url=url,
            location=locations_text,
            remote=self._is_remote(locations_text, title),
            salary=None,
            description=description,
            department=department,
            seniority=None,
            scraped_at=now,
        )

    def _is_remote(self, location: str | None, title: str) -> bool | None:
        text = f"{location or ''} {title}".lower()
        if "remote" in text:
            return True
        return None
