"""Onboarding wizard: steps 0–4."""

import asyncio
import logging

from fastapi import APIRouter, File, Request, UploadFile
from fastapi.responses import HTMLResponse, RedirectResponse

from jobpilot.ladder import compute_ladder
from jobpilot.pipeline import run_pipeline
from jobpilot.scrapers.adzuna import AdzunaScraper
from jobpilot.scrapers.jobspy_scraper import JobSpyScraper
from jobpilot.scrapers.jooble import JooblesScraper
from jobpilot.search_params import SearchParams
from jobpilot.steps.discover_companies import discover_companies
from jobpilot.steps.extract_resume import extract_resume

logger = logging.getLogger(__name__)
router = APIRouter()

_SENIORITY_PREFIXES = {
    "senior",
    "sr",
    "jr",
    "junior",
    "lead",
    "staff",
    "principal",
    "associate",
    "entry",
    "mid",
    "distinguished",
    "fellow",
}


def _core_title(title: str) -> str:
    """Strip leading seniority words so 'Senior Engineering Manager' → 'Engineering Manager'."""
    words = title.split()
    while words and words[0].lower().rstrip(".") in _SENIORITY_PREFIXES:
        words = words[1:]
    return " ".join(words) if words else title


def _default_keywords_from_profile(profile: dict) -> list[str]:
    """Derive search-friendly keyword suggestions from the extracted resume."""
    seen: set[str] = set()
    keywords: list[str] = []

    candidates: list[str] = []
    if profile.get("title"):
        candidates.append(profile["title"].strip())
    for exp in (profile.get("experience") or [])[:2]:
        for pos in (exp.get("positions") or [])[:1]:
            if pos.get("title"):
                candidates.append(pos["title"].strip())

    for raw in candidates:
        core = _core_title(raw)
        for kw in [core] if core == raw else [core, raw]:
            if kw and kw.lower() not in seen:
                seen.add(kw.lower())
                keywords.append(kw)

    return keywords[:4]


_MAX_UPLOAD_BYTES = 5 * 1024 * 1024  # 5 MB


# ---------------------------------------------------------------------------
# Root redirect
# ---------------------------------------------------------------------------


@router.get("/", response_class=HTMLResponse)
async def root(request: Request):
    profile_store = request.app.state.profile_store
    search_params_store = request.app.state.search_params_store
    db = request.app.state.db

    if not profile_store.has_profile():
        return RedirectResponse("/wizard/step/0")
    if not search_params_store.has_params():
        return RedirectResponse("/wizard/step/3")
    recent = db.get_recent_runs(limit=1)
    if recent:
        if recent[0].get("completed_at") is None:
            return RedirectResponse(f"/wizard/step/4?run_id={recent[0]['id']}")
        return RedirectResponse("/matches")
    return RedirectResponse("/wizard/step/4")


# ---------------------------------------------------------------------------
# Step 0 — Welcome
# ---------------------------------------------------------------------------


@router.get("/wizard/step/0", response_class=HTMLResponse)
async def step0_get(request: Request) -> HTMLResponse:
    return request.app.state.templates.TemplateResponse(
        request, "wizard.html", {"step": 0}
    )


# ---------------------------------------------------------------------------
# Step 1 — Resume upload
# ---------------------------------------------------------------------------


@router.get("/wizard/step/1", response_class=HTMLResponse)
async def step1_get(request: Request) -> HTMLResponse:
    return request.app.state.templates.TemplateResponse(
        request, "wizard.html", {"step": 1, "error": None}
    )


@router.post("/wizard/step/1", response_class=HTMLResponse)
async def step1_post(
    request: Request,
    file: UploadFile = File(...),
) -> HTMLResponse:
    templates = request.app.state.templates
    content = await file.read()

    if len(content) > _MAX_UPLOAD_BYTES:
        return templates.TemplateResponse(
            request, "wizard.html", {"step": 1, "error": "File too large (max 5 MB)."}
        )

    filename = file.filename or ""
    if not (filename.lower().endswith(".pdf") or filename.lower().endswith(".docx")):
        return templates.TemplateResponse(
            request,
            "wizard.html",
            {"step": 1, "error": "Please upload a PDF or DOCX file."},
        )

    try:
        profile = await asyncio.to_thread(
            extract_resume,
            content,
            filename,
            request.app.state.client,
            request.app.state.config,
            request.app.state.db,
        )
    except Exception as exc:
        logger.error(f"Resume extraction failed: {exc}")
        return templates.TemplateResponse(
            request, "wizard.html", {"step": 1, "error": f"Extraction failed: {exc}"}
        )

    request.app.state.profile_store.save_draft(profile)
    return RedirectResponse("/wizard/step/2", status_code=303)


# ---------------------------------------------------------------------------
# Step 2 — Confirm extracted resume
# ---------------------------------------------------------------------------


@router.get("/wizard/step/2", response_class=HTMLResponse)
async def step2_get(request: Request) -> HTMLResponse:
    profile_store = request.app.state.profile_store
    profile = profile_store.load_draft() or profile_store.load()
    if not profile:
        return RedirectResponse("/wizard/step/1")

    skills_flat = _flatten_skills(profile.get("skills") or {})
    return request.app.state.templates.TemplateResponse(
        request,
        "wizard.html",
        {
            "step": 2,
            "profile": profile,
            "skills_text": "\n".join(skills_flat),
            "low_confidence": set(profile.get("low_confidence_fields") or []),
        },
    )


@router.post("/wizard/step/2", response_class=HTMLResponse)
async def step2_post(request: Request) -> HTMLResponse:
    profile_store = request.app.state.profile_store
    profile = profile_store.load_draft() or profile_store.load() or {}
    form = await request.form()

    profile["name"] = form.get("name", profile.get("name", ""))
    profile["email"] = form.get("email", profile.get("email", ""))
    profile["phone"] = form.get("phone", profile.get("phone", ""))
    profile["location"] = form.get("location", profile.get("location", ""))
    profile["title"] = form.get("title", profile.get("title", ""))
    profile["summary"] = form.get("summary", profile.get("summary", ""))

    skills_raw = form.get("skills_text", "")
    skills_list = [
        s.strip() for s in skills_raw.replace(",", "\n").splitlines() if s.strip()
    ]
    profile["skills"] = {"Skills": skills_list} if skills_list else {}

    profile["low_confidence_fields"] = []
    profile_store.save_draft(profile)
    profile_store.commit_draft()

    async def _bg_score(app_state, committed_profile: dict) -> None:
        try:
            from jobpilot.steps.bullet_scorer import score_bullets

            scores = await asyncio.to_thread(
                score_bullets,
                committed_profile,
                app_state.client,
                app_state.config,
                app_state.db,
            )
            if scores:
                fresh = app_state.profile_store.load() or {}
                if fresh.get("experience") == committed_profile.get("experience"):
                    fresh["bullet_scores"] = scores
                    app_state.profile_store.save(fresh)
        except Exception as exc:
            logger.warning(f"Background bullet scoring failed: {exc}")

    _bg_task = asyncio.create_task(_bg_score(request.app.state, profile))
    background_tasks = request.app.state.background_tasks
    background_tasks.add(_bg_task)
    _bg_task.add_done_callback(background_tasks.discard)

    return RedirectResponse("/wizard/step/3", status_code=303)


# ---------------------------------------------------------------------------
# Step 3 — Search setup + company discovery
# ---------------------------------------------------------------------------


@router.get("/wizard/step/3", response_class=HTMLResponse)
async def step3_get(request: Request) -> HTMLResponse:
    sp = request.app.state.search_params_store.load()
    profile = request.app.state.profile_store.load()
    default_keywords = _default_keywords_from_profile(profile) if profile else []

    return request.app.state.templates.TemplateResponse(
        request,
        "wizard.html",
        {
            "step": 3,
            "sp": sp,
            "default_keywords": default_keywords,
            "suggestions": [],
        },
    )


@router.post("/wizard/step/3/find-similar", response_class=HTMLResponse)
async def step3_find_similar(request: Request) -> HTMLResponse:
    form = await request.form()
    anchors = [
        a.strip() for a in form.get("anchor_companies", "").splitlines() if a.strip()
    ]
    keywords = [k.strip() for k in form.get("keywords", "").split(",") if k.strip()]

    suggestions = await asyncio.to_thread(
        discover_companies,
        anchors,
        keywords,
        request.app.state.client,
        request.app.state.config,
        request.app.state.db,
    )
    return request.app.state.templates.TemplateResponse(
        request,
        "_partials/company_suggestions.html",
        {"suggestions": suggestions},
    )


@router.post("/wizard/step/3", response_class=HTMLResponse)
async def step3_post(request: Request) -> HTMLResponse:
    form = await request.form()

    keywords_raw = form.get("keywords", "")
    keywords = [k.strip() for k in keywords_raw.split(",") if k.strip()]

    anchors_raw = form.get("anchor_companies", "")
    anchor_companies = [a.strip() for a in anchors_raw.splitlines() if a.strip()]

    # Also pick up any checkboxes from the discovery suggestions
    extra = form.getlist("extra_companies")
    anchor_companies.extend(c for c in extra if c not in anchor_companies)

    sp = SearchParams(
        keywords=keywords,
        location=form.get("location", ""),
        radius_miles=int(form.get("radius_miles", 25)),
        remote_ok=form.get("remote_ok") == "on",
        seniority=form.get("seniority") or None,
        anchor_companies=anchor_companies,
    )
    request.app.state.search_params_store.save(sp)
    return RedirectResponse("/wizard/step/4", status_code=303)


# ---------------------------------------------------------------------------
# Step 4 — First run with polling progress
# ---------------------------------------------------------------------------


@router.get("/wizard/step/4", response_class=HTMLResponse)
async def step4_get(request: Request) -> HTMLResponse:
    """Start a pipeline run (if not already running) and show the progress page."""
    run_id_param = request.query_params.get("run_id")

    # If run_id provided, just show status for that run
    if run_id_param:
        try:
            run_id = int(run_id_param)
        except ValueError:
            return RedirectResponse("/wizard/step/4")
        return request.app.state.templates.TemplateResponse(
            request, "wizard.html", {"step": 4, "run_id": run_id}
        )

    # Start a new run
    profile = request.app.state.profile_store.load()
    sp = request.app.state.search_params_store.load()
    if not profile or not sp:
        return RedirectResponse("/wizard/step/1" if not profile else "/wizard/step/3")

    db = request.app.state.db
    config = request.app.state.config
    if compute_ladder(config, db)["state"] == "gift_exhausted":
        return RedirectResponse("/settings?key_exhausted=1", status_code=303)
    if db.count_runs_today() >= config.max_runs_per_day:
        return RedirectResponse("/matches?refresh_capped=1", status_code=303)
    client = request.app.state.client
    run_status = request.app.state.run_status

    run_id = db.start_run()
    run_status[run_id] = {"stage": "starting", "result": None, "error": None}

    scrapers = _build_scrapers(sp)

    def update_stage(stage: str) -> None:
        run_status[run_id]["stage"] = stage

    async def _run():
        try:
            result = await asyncio.to_thread(
                run_pipeline,
                db,
                profile,
                sp,
                config,
                scrapers,
                client,
                run_id,
                update_stage,
            )
            run_status[run_id]["stage"] = "done"
            run_status[run_id]["result"] = result
        except Exception as exc:
            logger.error(f"Pipeline run {run_id} failed: {exc}")
            run_status[run_id]["stage"] = "error"
            run_status[run_id]["error"] = str(exc)

    task = asyncio.create_task(_run())
    background_tasks = request.app.state.background_tasks
    background_tasks.add(task)
    task.add_done_callback(background_tasks.discard)
    return RedirectResponse(f"/wizard/step/4?run_id={run_id}", status_code=303)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _build_scrapers(sp) -> list:
    scrapers: list = [JobSpyScraper(sp)]
    if JooblesScraper.is_configured():
        scrapers.append(JooblesScraper(sp))
    if AdzunaScraper.is_configured():
        scrapers.append(AdzunaScraper(sp))
    return scrapers


def _flatten_skills(skills: dict | list) -> list[str]:
    if isinstance(skills, list):
        return [str(s) for s in skills]
    result = []
    for items in skills.values():
        if isinstance(items, list):
            result.extend(str(s) for s in items)
    return result
