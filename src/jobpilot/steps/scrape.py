import logging
from concurrent.futures import ThreadPoolExecutor, as_completed

from jobpilot.db import Database
from jobpilot.scrapers.base import BaseScraper, RawJob

logger = logging.getLogger(__name__)


def _scrape_one(scraper: BaseScraper) -> tuple[str, list[RawJob], Exception | None]:
    try:
        return scraper.company_name, scraper.fetch_jobs(), None
    except Exception as e:
        return scraper.company_name, [], e


def run_scrape(db: Database, scrapers: list[BaseScraper]) -> dict:
    total_scraped = 0
    all_new_ids = []
    failed_companies = []

    # Fetch from all scrapers concurrently; DB writes happen serially after
    with ThreadPoolExecutor(max_workers=max(len(scrapers), 1)) as executor:
        futures = {executor.submit(_scrape_one, s): s for s in scrapers}
        results = [f.result() for f in as_completed(futures)]

    for company, jobs, error in results:
        if error:
            logger.error(f"Failed to scrape {company}: {error}")
            failed_companies.append(company)
            continue

        if not jobs:
            logger.warning(f"No jobs returned from {company}")
            failed_companies.append(company)
            continue

        candidate_ids = [job.db_id for job in jobs]
        new_ids = db.get_new_job_ids(candidate_ids)

        for job in jobs:
            db.upsert_job(
                id=job.db_id,
                company=job.company,
                title=job.title,
                url=job.url,
                location=job.location,
                remote=job.remote,
                salary=job.salary,
                description=job.description,
                department=job.department,
                seniority=job.seniority,
                scraped_at=job.scraped_at,
            )
        db.commit()

        db.close_missing_jobs(company, current_ids=candidate_ids)

        all_new_ids.extend(new_ids)
        total_scraped += len(jobs)
        logger.info(f"{company}: {len(jobs)} total, {len(new_ids)} new")

    return {
        "jobs_scraped": total_scraped,
        "new_jobs": len(all_new_ids),
        "new_job_ids": all_new_ids,
        "failed_companies": failed_companies,
    }
