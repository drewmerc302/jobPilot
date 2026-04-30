import logging
import os
from datetime import datetime, timezone

import httpx
from tenacity import (
    retry,
    retry_if_exception_type,
    stop_after_attempt,
    wait_exponential,
)

from jobpilot.scrapers.base import BaseScraper, RawJob
from jobpilot.search_params import SearchParams

logger = logging.getLogger(__name__)

ADZUNA_BASE = "https://api.adzuna.com/v1/api/jobs/us/search"
RESULTS_PER_PAGE = 50
MAX_PAGES = 3  # 3 pages × up to 2 calls (geo + remote) = 6 API calls/refresh

_http_retry = retry(
    stop=stop_after_attempt(3),
    wait=wait_exponential(multiplier=1, min=2, max=10),
    retry=retry_if_exception_type((httpx.HTTPError, httpx.TimeoutException)),
    reraise=True,
)


class AdzunaScraper(BaseScraper):
    source = "adzuna"
    company_name = "adzuna"
    tracks_full_company_listing = False

    def __init__(self, search_params: SearchParams):
        self.search_params = search_params
        self._app_id = os.environ.get("ADZUNA_APP_ID", "")
        self._app_key = os.environ.get("ADZUNA_APP_KEY", "")

    @classmethod
    def is_configured(cls) -> bool:
        return bool(
            os.environ.get("ADZUNA_APP_ID") and os.environ.get("ADZUNA_APP_KEY")
        )

    def fetch_jobs(self) -> list[RawJob]:
        if not self.search_params.location:
            raise RuntimeError(
                "AdzunaScraper requires a location string in SearchParams."
            )

        seen_ids: set[str] = set()
        raw_items = self._paginate(remote=False, seen_ids=seen_ids)
        if self.search_params.remote_ok:
            raw_items += self._paginate(remote=True, seen_ids=seen_ids)

        logger.info(
            f"Adzuna: {len(raw_items)} unique jobs "
            f"({'geo + remote' if self.search_params.remote_ok else 'geo only'})"
        )
        return [self._to_raw_job(item, is_remote) for item, is_remote in raw_items]

    def _paginate(self, remote: bool, seen_ids: set[str]) -> list[tuple[dict, bool]]:
        results = []
        for page in range(1, MAX_PAGES + 1):
            items = self._fetch_page(page, remote=remote)
            if items is None:
                break  # request failed — stop paginating
            if not items:
                break  # genuine end of results
            new = [i for i in items if i["id"] not in seen_ids]
            seen_ids.update(i["id"] for i in new)
            results.extend((i, remote) for i in new)
        return results

    def _fetch_page(self, page: int, remote: bool) -> list[dict] | None:
        """Returns items on success, [] on empty page, None on request failure."""
        params = self._build_params(remote=remote)
        try:
            resp = self._get_with_retry(f"{ADZUNA_BASE}/{page}", params)
            return resp.json().get("results", [])
        except Exception as e:
            label = "remote" if remote else "geo"
            logger.error(f"Adzuna {label} page {page} failed: {e}")
            return None

    @_http_retry
    def _get_with_retry(self, url: str, params: dict) -> httpx.Response:
        resp = httpx.get(url, params=params, timeout=30)
        resp.raise_for_status()
        return resp

    def _build_params(self, remote: bool) -> dict:
        sp = self.search_params
        keywords = list(sp.keywords)
        if sp.seniority:
            keywords.append(sp.seniority)

        params: dict = {
            "app_id": self._app_id,
            "app_key": self._app_key,
            "results_per_page": RESULTS_PER_PAGE,
            "what": " ".join(keywords),
            "sort_by": "date",
            "content-type": "application/json",
        }

        if remote:
            params["remote"] = 1
        else:
            params["where"] = sp.location

        return params

    def _to_raw_job(self, item: dict, is_remote_search: bool) -> RawJob:
        location_str = item.get("location", {}).get("display_name")
        remote = is_remote_search or bool(
            location_str and "remote" in location_str.lower()
        )

        salary = None
        sal_min = item.get("salary_min")
        sal_max = item.get("salary_max")
        if sal_min and sal_max:
            salary = f"${sal_min:,.0f} – ${sal_max:,.0f}"
        elif sal_min:
            salary = f"${sal_min:,.0f}+"
        elif sal_max:
            salary = f"up to ${sal_max:,.0f}"

        return RawJob(
            external_id=str(item["id"]),
            company=item.get("company", {}).get("display_name") or "Unknown",
            title=item.get("title") or "Unknown Title",
            url=item.get("redirect_url") or item.get("url", ""),
            location=location_str,
            remote=remote,
            salary=salary,
            description=item.get("description"),
            department=item.get("category", {}).get("label"),
            seniority=None,
            scraped_at=datetime.now(timezone.utc),
        )
