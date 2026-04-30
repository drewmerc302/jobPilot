import logging
import time

import anthropic

from jobpilot.config import Config
from jobpilot.db import Database
from jobpilot.geocode import geocode
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
            positions = exp.get("positions") or []
            title = exp.get("title") or (
                positions[0].get("title", "") if positions else ""
            )
            parts.append(f"{title} at {exp.get('company', '')}")
    return "\n".join(parts)


def run_pipeline(
    db: Database,
    resume_data: dict,
    search_params: SearchParams,
    config: Config,
    scrapers: list[BaseScraper],
    client=None,
    run_id: int | None = None,
    stage_updater=None,
) -> dict:
    """Run the full scrape → dedup → filter pipeline.

    Called by the FastAPI layer on refresh (auto on open, manual button).
    Returns a summary dict for the in-app toast notification.

    resume_data is passed explicitly — storage location is a Phase 2 concern.
    client is optional; created internally if not provided.
    run_id is optional; created internally if not provided.
    """
    if client is None:
        client = anthropic.Anthropic(api_key=config.anthropic_api_key, timeout=90)

    start_time = time.time()
    if run_id is None:
        run_id = db.start_run()

    def _set_stage(stage: str) -> None:
        db.update_run_stage(run_id, stage)
        if stage_updater:
            stage_updater(stage)

    try:
        _set_stage("scraping")
        geocode(search_params)
        resume_summary = get_resume_summary(resume_data)

        scrape_result = run_scrape(db, scrapers)
        logger.info(
            f"Scrape complete: {scrape_result['jobs_scraped']} jobs, "
            f"{scrape_result['new_jobs']} new"
        )

        run_dedup(db)
        _set_stage("filtering")

        new_job_ids = scrape_result["new_job_ids"]
        matches = run_filter(
            db,
            new_job_ids,
            resume_summary,
            search_params,
            config,
            client=client,
            run_id=run_id,
        )
        logger.info(f"Filter complete: {len(matches)} matches")
        _set_stage("done")

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
