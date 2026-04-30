import logging
import math
from datetime import datetime, timezone

from jobpilot.scrapers.base import BaseScraper, RawJob
from jobpilot.search_params import SearchParams

logger = logging.getLogger(__name__)


def _val(v, default=None):
    """Return None for pandas NaN/None/empty, otherwise the value."""
    if v is None:
        return default
    try:
        if isinstance(v, float) and math.isnan(v):
            return default
    except (TypeError, ValueError):
        pass
    return v if v != "" else default


class JobSpyScraper(BaseScraper):
    source = "jobspy"
    company_name = "jobspy"
    tracks_full_company_listing = False

    def __init__(self, search_params: SearchParams):
        self.search_params = search_params

    def fetch_jobs(self) -> list[RawJob]:
        from jobspy import scrape_jobs  # lazy import — heavy dep

        sp = self.search_params
        keyword_str = " ".join(sp.keywords) if sp.keywords else ""

        sites = ["indeed", "zip_recruiter", "google"]
        results = []

        # Geo search
        if sp.location:
            try:
                df = scrape_jobs(
                    site_name=sites,
                    search_term=keyword_str,
                    location=sp.location,
                    distance=sp.radius_miles,
                    results_wanted=50,
                    hours_old=72,
                    verbose=0,
                )
                results.extend(self._df_to_raw(df))
            except Exception as exc:
                logger.warning(f"JobSpy geo search failed: {exc}")

        # Remote-only pass
        if sp.remote_ok:
            try:
                df = scrape_jobs(
                    site_name=sites,
                    search_term=keyword_str + " remote",
                    is_remote=True,
                    results_wanted=30,
                    hours_old=72,
                    verbose=0,
                )
                results.extend(self._df_to_raw(df))
            except Exception as exc:
                logger.warning(f"JobSpy remote search failed: {exc}")

        seen: set[str] = set()
        deduped = []
        for job in results:
            if job.db_id not in seen:
                seen.add(job.db_id)
                deduped.append(job)
        return deduped

    def _df_to_raw(self, df) -> list[RawJob]:
        jobs = []
        now = datetime.now(timezone.utc)
        for _, row in df.iterrows():
            try:
                external_id = _val(row.get("id")) or _val(row.get("job_url"), "unknown")
                company = _val(row.get("company"), "Unknown")
                title = _val(row.get("title"), "")
                url = _val(row.get("job_url"), "")
                if not title or not url:
                    continue

                location = _val(row.get("location"))
                is_remote = bool(_val(row.get("is_remote"), False))

                min_amt = _val(row.get("min_amount"))
                max_amt = _val(row.get("max_amount"))
                interval = _val(row.get("interval"))
                if min_amt and max_amt:
                    salary = f"${float(min_amt):,.0f}–${float(max_amt):,.0f}{' ' + interval if interval else ''}"
                elif min_amt:
                    salary = (
                        f"${float(min_amt):,.0f}+{' ' + interval if interval else ''}"
                    )
                else:
                    salary = None

                jobs.append(
                    RawJob(
                        external_id=str(external_id),
                        company=str(company),
                        title=str(title),
                        url=str(url),
                        location=location,
                        remote=is_remote,
                        salary=salary,
                        description=_val(row.get("description")),
                        department=_val(row.get("job_function")),
                        seniority=_val(row.get("job_level")),
                        scraped_at=now,
                    )
                )
            except Exception as exc:
                logger.debug(f"JobSpy row mapping failed: {exc}")
        return jobs
