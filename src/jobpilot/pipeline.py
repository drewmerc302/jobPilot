import logging
import time

from jobpilot.config import Config
from jobpilot.db import Database
from jobpilot.scrapers.base import BaseScraper
from jobpilot.search_params import SearchParams
from jobpilot.steps.dedup import run_dedup
from jobpilot.steps.filter import run_filter
from jobpilot.steps.scrape import run_scrape

logger = logging.getLogger(__name__)


def get_resume_summary(resume_data: dict) -> str:
    """Distill resume YAML into a short text block for the Haiku filter prompt.

    resume_data is passed explicitly — storage location is a Phase 2 concern.
    """
    parts = []
    if summary := resume_data.get("summary"):
        parts.append(summary)
    if skills := resume_data.get("skills"):
        if isinstance(skills, list):
            parts.append("Skills: " + ", ".join(str(s) for s in skills[:15]))
        elif isinstance(skills, dict):
            for cat, items in skills.items():
                if isinstance(items, list):
                    parts.append(f"{cat}: {', '.join(str(i) for i in items[:10])}")
    if experience := resume_data.get("experience"):
        for exp in experience[:3]:
            parts.append(f"{exp.get('title', '')} at {exp.get('company', '')}")
    return "\n".join(parts)


def run_pipeline(
    db: Database,
    resume_data: dict,
    search_params: SearchParams,
    config: Config,
    scrapers: list[BaseScraper],
) -> dict:
    """Run the full scrape → dedup → filter pipeline.

    Called by the FastAPI layer on refresh (auto on open, manual button).
    Returns a summary dict for the in-app toast notification.

    resume_data is passed explicitly — storage location is a Phase 2 concern.
    """
    start_time = time.time()
    run_id = db.start_run()

    try:
        resume_summary = get_resume_summary(resume_data)

        scrape_result = run_scrape(db, scrapers)
        logger.info(
            f"Scrape complete: {scrape_result['jobs_scraped']} jobs, "
            f"{scrape_result['new_jobs']} new"
        )

        run_dedup(db)

        new_job_ids = scrape_result["new_job_ids"]
        matches = run_filter(db, new_job_ids, resume_summary, search_params, config)
        logger.info(f"Filter complete: {len(matches)} matches")

        duration = f"{time.time() - start_time:.1f}s"
        db.complete_run(
            run_id,
            jobs_scraped=scrape_result["jobs_scraped"],
            new_jobs=scrape_result["new_jobs"],
            matches_found=len(matches),
        )
        logger.info(f"Pipeline complete in {duration}")

        return {
            "jobs_scraped": scrape_result["jobs_scraped"],
            "new_jobs": scrape_result["new_jobs"],
            "new_matches": len(matches),
            "failed_companies": scrape_result["failed_companies"],
            "duration": duration,
        }

    except Exception as e:
        logger.error(f"Pipeline failed: {e}")
        db.complete_run(
            run_id, jobs_scraped=0, new_jobs=0, matches_found=0, error=str(e)
        )
        raise
