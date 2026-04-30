import logging
import os
from datetime import datetime, timezone

import httpx

from jobpilot.scrapers.base import BaseScraper, RawJob
from jobpilot.search_params import SearchParams

logger = logging.getLogger(__name__)

_JOOBLE_URL = "https://jooble.org/api/{key}"


class JooblesScraper(BaseScraper):
    source = "jooble"
    company_name = "jooble"
    tracks_full_company_listing = False

    def __init__(self, search_params: SearchParams):
        self.search_params = search_params
        self._api_key = os.environ.get("JOOBLE_API_KEY", "")

    @classmethod
    def is_configured(cls) -> bool:
        return bool(os.environ.get("JOOBLE_API_KEY"))

    def fetch_jobs(self) -> list[RawJob]:
        sp = self.search_params
        keywords = " ".join(sp.keywords) if sp.keywords else ""
        jobs = []

        # Geo search
        if sp.location:
            jobs.extend(self._fetch(keywords, sp.location))

        # Remote pass
        if sp.remote_ok:
            jobs.extend(self._fetch(keywords + " remote", "", force_remote=True))

        seen: set[str] = set()
        deduped = []
        for job in jobs:
            if job.db_id not in seen:
                seen.add(job.db_id)
                deduped.append(job)
        return deduped

    def _fetch(
        self, keywords: str, location: str, force_remote: bool = False
    ) -> list[RawJob]:
        url = _JOOBLE_URL.format(key=self._api_key)
        payload: dict = {"keywords": keywords}
        if location:
            payload["location"] = location

        try:
            resp = httpx.post(url, json=payload, timeout=15)
            resp.raise_for_status()
            data = resp.json()
        except Exception as exc:
            logger.warning(f"Jooble API call failed: {exc}")
            return []

        now = datetime.now(timezone.utc)
        results = []
        for item in data.get("jobs", []):
            try:
                external_id = str(item.get("id", ""))
                title = (item.get("title") or "").strip()
                url_str = (item.get("link") or "").strip()
                if not external_id or not title or not url_str:
                    continue

                location_str = (item.get("location") or "").strip() or None
                company = (item.get("company") or "Unknown").strip()
                salary = (item.get("salary") or "").strip() or None
                snippet = (item.get("snippet") or "").strip() or None
                is_remote = (
                    force_remote
                    or bool(location_str and "remote" in location_str.lower())
                    or "remote" in title.lower()
                )

                results.append(
                    RawJob(
                        external_id=external_id,
                        company=company,
                        title=title,
                        url=url_str,
                        location=location_str,
                        remote=is_remote,
                        salary=salary,
                        description=snippet,
                        department=None,
                        seniority=None,
                        scraped_at=now,
                    )
                )
            except Exception as exc:
                logger.debug(f"Jooble item mapping failed: {exc}")
        return results
