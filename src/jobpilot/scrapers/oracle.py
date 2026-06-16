import logging
import re
import time
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

_http_retry = retry(
    stop=stop_after_attempt(3),
    wait=wait_exponential(multiplier=1, min=2, max=10),
    retry=retry_if_exception_type((httpx.HTTPError, httpx.TimeoutException)),
    reraise=True,
)

# Curated tenant map: lets users add well-known Oracle HCM employers by name
# with zero friction. Keys are lowercased company names (+ aliases). Values are
# (tenant, site_number) and must be VERIFIED real values — a wrong tenant
# silently scrapes nothing. Only add entries confirmed against the live board.
_TENANT_MAP: dict[str, tuple[str, str]] = {
    "jpmorganchase": ("jpmc", "CX_1001"),
    "jpmorgan chase": ("jpmc", "CX_1001"),
    "jpmc": ("jpmc", "CX_1001"),
}

_ORACLE_HOST_RE = re.compile(r"https?://([a-z0-9-]+)\.fa\.oraclecloud\.com", re.I)
_ORACLE_SITE_RE = re.compile(r"/sites/([^/?#]+)")


class OracleProbeError(Exception):
    """Server-side issue (5xx, timeout, connection) — distinct from 'not Oracle'."""


def _parse_oracle_url(url: str) -> tuple[str, str] | None:
    """Extract (tenant, site_number) from an Oracle careers URL.

    Returns None if the URL is not a recognizable `*.fa.oraclecloud.com` link.
    site_number defaults to CX_1001 when the URL omits the `/sites/<n>/` segment.
    """
    if not url:
        return None
    host = _ORACLE_HOST_RE.search(url)
    if not host:
        return None
    tenant = host.group(1).lower()
    site_m = _ORACLE_SITE_RE.search(url)
    site_number = site_m.group(1) if site_m else "CX_1001"
    return tenant, site_number


def probe_oracle(
    company_name: str,
    *,
    keywords: list[str] | None = None,
    url: str | None = None,
) -> "OracleScraper | None":
    """Resolve an Oracle HCM board for a company.

    Precedence:
      1. curated tenant map — zero friction for known employers
      2. a user-provided careers URL — catch-all for the long tail
      3. None — not resolvable as Oracle; the caller's other ATS probes still run

    Oracle tenants are opaque ids with no slug convention, so there is no blind
    name-based probe (hence map/URL). Resolution does no network I/O;
    OracleProbeError exists for signature parity with the other probes and for
    any future live-validation caller.
    """
    key = company_name.strip().lower()
    resolved = _TENANT_MAP.get(key) or _parse_oracle_url(url or "")
    if resolved is None:
        return None
    tenant, site_number = resolved
    logger.info(
        "Oracle board resolved: %r → tenant=%s site=%s",
        company_name,
        tenant,
        site_number,
    )
    return OracleScraper(
        company_name=company_name,
        tenant=tenant,
        site_number=site_number,
        keyword_patterns=keywords or [],
    )


class OracleScraper(BaseScraper):
    """Oracle HCM Cloud (Oracle Recruiting CE) scraper.

    Used by employers like JPMorganChase, Citi, BofA, Disney, etc. that host
    requisitions on `{tenant}.fa.oraclecloud.com`. The listing response lacks
    full descriptions, so a per-req detail fetch is needed — the public job page
    is a JS SPA, so jobPilot's lazy URL fetcher cannot recover the description.
    """

    source = "oracle"
    tracks_full_company_listing = True

    def __init__(
        self,
        company_name: str,
        tenant: str,
        site_number: str = "CX_1001",
        keyword_patterns: list[str] | None = None,
        countries: list[str] | None = None,
        keyword_search: str = "",
        page_size: int = 200,
        request_delay: float = 1.0,
        max_pages: int = 25,
        max_details: int = 200,
    ):
        self.company_name = company_name
        self.tenant = tenant
        self.site_number = site_number
        # Title prefilter (lowercased) to bound the per-req detail fetch. Empty
        # = no prefilter; jobPilot's filter step does the real matching.
        self.keyword_patterns = [k.lower() for k in (keyword_patterns or [])]
        self.countries = countries or ["US"]
        self.keyword_search = keyword_search
        self.page_size = page_size
        self.request_delay = request_delay
        self.max_pages = max_pages
        self.max_details = max_details

    @property
    def base_url(self) -> str:
        return f"https://{self.tenant}.fa.oraclecloud.com"

    def _title_matches(self, title: str) -> bool:
        if not self.keyword_patterns:
            return True
        title_lower = title.lower()
        return any(kw in title_lower for kw in self.keyword_patterns)

    def fetch_jobs(self) -> list[RawJob]:
        try:
            with httpx.Client(
                timeout=30,
                headers={
                    "User-Agent": "jobPilot/1.0",
                    "Accept": "application/json",
                },
            ) as client:
                all_reqs = self._fetch_all_listings(client)
                relevant = [
                    r
                    for r in all_reqs
                    if (
                        not self.countries
                        or r.get("PrimaryLocationCountry") in self.countries
                    )
                    and self._title_matches(r.get("Title", ""))
                ]
                if len(relevant) > self.max_details:
                    logger.warning(
                        "%s: %d Oracle reqs match filter, capping detail fetch at %d",
                        self.company_name,
                        len(relevant),
                        self.max_details,
                    )
                    relevant = relevant[: self.max_details]
                logger.info(
                    "%s: %d of %d Oracle reqs match filter, fetching details",
                    self.company_name,
                    len(relevant),
                    len(all_reqs),
                )
                now = datetime.now(timezone.utc)
                jobs = []
                for i, r in enumerate(relevant):
                    if i > 0:
                        time.sleep(self.request_delay)
                    detail = self._fetch_detail(client, str(r.get("Id", "")))
                    merged = {**r, **(detail or {})}
                    jobs.append(self._parse_req(merged, now))
                return jobs
        except Exception as e:
            logger.error(f"Failed to fetch {self.company_name} Oracle jobs: {e}")
            return []

    def _fetch_all_listings(self, client: httpx.Client) -> list[dict]:
        all_reqs: list[dict] = []
        offset = 0
        total = None
        for _ in range(self.max_pages):
            resp = self._get_listings_page(client, offset)
            data = resp.json()
            items = data.get("items", [])
            if not items:
                break
            search = items[0]
            reqs = search.get("requisitionList", [])
            if not reqs:
                break
            all_reqs.extend(reqs)
            total = search.get("TotalJobsCount", total)
            offset += self.page_size
            if total is not None and offset >= total:
                break
            time.sleep(self.request_delay)
        return all_reqs

    def _fetch_detail(self, client: httpx.Client, req_id: str) -> dict | None:
        if not req_id:
            return None
        try:
            resp = self._get_detail_page(client, req_id)
            items = resp.json().get("items", [])
            return items[0] if items else None
        except Exception as e:
            logger.warning(f"Failed to fetch Oracle detail for {req_id}: {e}")
            return None

    @_http_retry
    def _get_detail_page(self, client: httpx.Client, req_id: str) -> httpx.Response:
        url = (
            f"{self.base_url}/hcmRestApi/resources/latest/"
            "recruitingCEJobRequisitionDetails"
        )
        params = {
            "onlyData": "true",
            "expand": "all",
            "finder": f"ById;Id={req_id},siteNumber={self.site_number}",
        }
        resp = client.get(url, params=params)
        resp.raise_for_status()
        return resp

    @_http_retry
    def _get_listings_page(self, client: httpx.Client, offset: int) -> httpx.Response:
        finder_parts = [f"siteNumber={self.site_number}"]
        if self.keyword_search:
            finder_parts.append(f"keyword={self.keyword_search}")
        finder_parts += [
            f"limit={self.page_size}",
            f"offset={offset}",
            "sortBy=POSTING_DATES_DESC",
        ]
        finder = "findReqs;" + ",".join(finder_parts)
        params = {
            "onlyData": "true",
            "expand": "requisitionList",
            "finder": finder,
        }
        url = f"{self.base_url}/hcmRestApi/resources/latest/recruitingCEJobRequisitions"
        resp = client.get(url, params=params)
        resp.raise_for_status()
        return resp

    def _parse_req(self, r: dict, now: datetime) -> RawJob:
        req_id = str(r.get("Id", ""))
        description = self._compose_description(r)
        # NOTE: jobPilot's RawJob has no `source` field — source is carried as the
        # scraper class attribute and read by steps/scrape.py. Do not pass it here.
        return RawJob(
            external_id=req_id,
            company=self.company_name,
            title=r.get("Title", ""),
            url=self._build_url(req_id),
            location=r.get("PrimaryLocation"),
            remote=self._extract_remote(r),
            salary=self._extract_salary(description),
            description=description or None,
            department=r.get("Department") or r.get("JobFamily"),
            seniority=r.get("ManagerLevel"),
            scraped_at=now,
        )

    def _build_url(self, req_id: str) -> str:
        return (
            f"{self.base_url}/hcmUI/CandidateExperience/en/sites/"
            f"{self.site_number}/job/{req_id}"
        )

    def _compose_description(self, r: dict) -> str:
        parts = [
            r.get("ShortDescriptionStr") or "",
            r.get("ExternalDescriptionStr") or "",
            r.get("ExternalResponsibilitiesStr") or "",
            r.get("ExternalQualificationsStr") or "",
            r.get("CorporateDescriptionStr") or "",
        ]
        return "\n\n".join(p for p in parts if p)

    def _extract_remote(self, r: dict) -> bool | None:
        code = (r.get("WorkplaceTypeCode") or "").upper()
        if code in {"REMOTE", "FULLY_REMOTE"}:
            return True
        if code in {"ONSITE", "ON_SITE", "HYBRID"}:
            return False
        loc = (r.get("PrimaryLocation") or "").lower()
        if "remote" in loc:
            return True
        return None

    def _extract_salary(self, text: str) -> str | None:
        if not text:
            return None
        patterns = [
            r"\$[\d,]+\s*[-–]\s*\$[\d,]+",
            r"\$[\d,]+(?:\.\d{2})?",
        ]
        for pattern in patterns:
            m = re.search(pattern, text)
            if m:
                return m.group(0)
        return None

    def is_job_live(self, url: str) -> bool | None:
        try:
            resp = httpx.get(url, timeout=10, follow_redirects=True)
            if resp.status_code in (404, 410):
                return False
            if resp.status_code == 200:
                text = resp.text.lower()
                if "no longer available" in text or "not found" in text:
                    return False
                return True
            return None
        except Exception:
            return None
