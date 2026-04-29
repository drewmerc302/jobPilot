"""Matches list, job detail, status management, tailoring, and interview prep."""

import asyncio
import json
import logging
from pathlib import Path

from fastapi import APIRouter, Form, Request
from fastapi.responses import HTMLResponse, RedirectResponse

from jobpilot.ladder import compute_ladder
from jobpilot.steps.interview_prep import generate_interview_prep
from jobpilot.steps.tailor import ensure_analysis, run_tailor_for_job

logger = logging.getLogger(__name__)
router = APIRouter()


@router.get("/matches", response_class=HTMLResponse)
async def matches_list(request: Request) -> HTMLResponse:
    db = request.app.state.db
    config = request.app.state.config
    matches = db.get_all_applications()
    spent = db.sum_costs_this_month()
    sp = request.app.state.search_params_store.load()
    refresh_capped = request.query_params.get("refresh_capped")
    ladder = compute_ladder(config, db)
    return request.app.state.templates.TemplateResponse(
        request,
        "matches.html",
        {
            "matches": matches,
            "spent": spent,
            "budget": config.monthly_budget,
            "sp": sp,
            "refresh_capped": refresh_capped,
            "ladder": ladder,
        },
    )


@router.get("/matches/{job_id}", response_class=HTMLResponse)
async def job_detail(job_id: str, request: Request) -> HTMLResponse:
    db = request.app.state.db
    config = request.app.state.config
    job = db.get_job(job_id)
    if not job:
        return RedirectResponse("/matches")
    match = db.get_match(job_id)
    application = db.get_application(job_id)
    spent = db.sum_costs_this_month()

    suggestions = {}
    if match and match.get("suggestions"):
        try:
            suggestions = json.loads(match["suggestions"])
        except Exception:
            pass

    prep_result = None
    if match and match.get("interview_prep_path"):
        try:
            prep_result = json.loads(Path(match["interview_prep_path"]).read_text())
        except Exception:
            pass

    ladder = compute_ladder(config, db)
    return request.app.state.templates.TemplateResponse(
        request,
        "job_detail.html",
        {
            "job": job,
            "match": match,
            "application": application,
            "suggestions": suggestions,
            "prep_result": prep_result,
            "spent": spent,
            "budget": config.monthly_budget,
            "job_id": job["id"],
            "status": application["status"] if application else "new",
            "ladder": ladder,
        },
    )


@router.post("/matches/{job_id}/status", response_class=HTMLResponse)
async def update_status(
    job_id: str,
    request: Request,
    status: str = Form(...),
) -> HTMLResponse:
    db = request.app.state.db
    db.set_application_status(job_id, status)
    application = db.get_application(job_id)
    job = db.get_job(job_id)
    return request.app.state.templates.TemplateResponse(
        request,
        "_partials/status_badge.html",
        {
            "job_id": job_id,
            "status": status,
            "job": job,
            "application": application,
        },
    )


@router.post("/matches/{job_id}/dismiss", response_class=HTMLResponse)
async def dismiss_match(job_id: str, request: Request) -> HTMLResponse:
    request.app.state.db.dismiss_match(job_id)
    # Empty response — HTMX removes the row via hx-swap="outerHTML"
    return HTMLResponse("")


@router.post("/matches/{job_id}/tailor", response_class=HTMLResponse)
async def tailor_match(job_id: str, request: Request) -> HTMLResponse:
    """Synchronous tailor for Pass 1. Returns result partial when done."""
    db = request.app.state.db
    config = request.app.state.config
    client = request.app.state.client
    templates = request.app.state.templates

    if compute_ladder(config, db)["state"] == "gift_exhausted":
        return HTMLResponse(
            "<span class='error'>Starter credit used up. <a href='/settings'>Add your own key →</a></span>"
        )

    job = db.get_job(job_id)
    if not job:
        return HTMLResponse("<span class='error'>Job not found</span>")

    profile = request.app.state.profile_store.load()
    if not profile:
        return HTMLResponse(
            "<span class='error'>Profile not found — complete onboarding first</span>"
        )

    try:
        analysis = ensure_analysis(job, profile, db, config, client=client)
        output_dir = config.output_dir / job_id
        result = run_tailor_for_job(job, analysis, profile, output_dir, config)
        if result.get("resume_pdf"):
            db.update_match_paths(job_id, resume_path=str(result["resume_pdf"]))
        return templates.TemplateResponse(
            request,
            "_partials/tailor_result.html",
            {
                "job_id": job_id,
                "result": result,
                "analysis": analysis,
            },
        )
    except Exception as exc:
        logger.error(f"Tailor failed for {job_id}: {exc}")
        return HTMLResponse(f"<span class='error'>Tailor failed: {exc}</span>")


@router.post("/matches/{job_id}/interview-prep", response_class=HTMLResponse)
async def interview_prep_match(job_id: str, request: Request) -> HTMLResponse:
    db = request.app.state.db
    config = request.app.state.config
    client = request.app.state.client
    templates = request.app.state.templates

    if compute_ladder(config, db)["state"] == "gift_exhausted":
        return HTMLResponse(
            "<span class='error'>Starter credit used up. <a href='/settings'>Add your own key →</a></span>"
        )

    job = db.get_job(job_id)
    if not job:
        return HTMLResponse("<span class='error'>Job not found</span>")

    profile = request.app.state.profile_store.load()
    if not profile:
        return HTMLResponse(
            "<span class='error'>Profile not found — complete onboarding first</span>"
        )

    try:
        prep_result = await asyncio.to_thread(
            generate_interview_prep,
            db,
            job_id,
            profile,
            config,
            client,
        )
        if prep_result is None:
            return HTMLResponse(
                "<span class='error'>Interview prep failed — please try again.</span>"
            )
        output_dir = config.output_dir / job_id
        output_dir.mkdir(parents=True, exist_ok=True)
        prep_path = output_dir / "interview_prep.json"
        prep_path.write_text(json.dumps(prep_result, ensure_ascii=False, indent=2))
        db.update_match_paths(job_id, interview_prep_path=str(prep_path))
        return templates.TemplateResponse(
            request,
            "_partials/interview_prep_result.html",
            {"prep_result": prep_result},
        )
    except Exception as exc:
        logger.error(f"Interview prep failed for {job_id}: {exc}")
        return HTMLResponse(f"<span class='error'>Interview prep failed: {exc}</span>")
