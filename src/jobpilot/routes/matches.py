"""Matches list, job detail, status management, tailoring, and interview prep."""

import asyncio
import hashlib
import html as html_mod
import ipaddress
import json
import logging
import re
import socket
from pathlib import Path
from urllib.parse import parse_qsl, urlencode, urlparse, urlunparse

from fastapi import APIRouter, Form, Request
from fastapi.responses import FileResponse, HTMLResponse, RedirectResponse

from jobpilot.fetch_description import fetch_full_description, is_snippet
from jobpilot.ladder import compute_ladder
from jobpilot.pipeline import run_pipeline
from jobpilot.scrapers.adzuna import AdzunaScraper
from jobpilot.scrapers.greenhouse import GreenhouseProbeError, probe_greenhouse
from jobpilot.scrapers.jobspy_scraper import JobSpyScraper
from jobpilot.scrapers.lever import LeverProbeError, probe_lever
from jobpilot.scrapers.workday import WorkdayProbeError, probe_workday
from jobpilot.scrapers.jooble import JooblesScraper
from jobpilot.steps.interview_prep import (
    generate_interview_prep,
    generate_interview_prep_pdf,
)
from jobpilot.steps.tailor import (
    PdfGenerationError,
    ensure_analysis,
    run_tailor_for_job,
)

logger = logging.getLogger(__name__)
router = APIRouter()

_STRIP_PARAMS = re.compile(
    r"^(utm_|fbclid|gclid|refId|ref_|mc_|ck_|trk|campaignid|adgroupid)", re.IGNORECASE
)


def _is_safe_url(url: str) -> bool:
    try:
        p = urlparse(url)
        if p.scheme not in ("http", "https"):
            return False
        host = p.hostname
        if not host:
            return False
        if (
            host in ("localhost",)
            or host.endswith(".local")
            or host.endswith(".internal")
        ):
            return False
        # Resolve host to every address family it advertises and reject if any
        # resolves into a private/loopback/link-local/reserved range. Catches
        # the case where a public hostname points at an internal IP.
        try:
            infos = socket.getaddrinfo(host, None)
        except (socket.gaierror, UnicodeError):
            return False
        for _family, _type, _proto, _canon, sockaddr in infos:
            ip_str = sockaddr[0]
            try:
                addr = ipaddress.ip_address(ip_str)
            except ValueError:
                return False
            if (
                addr.is_private
                or addr.is_loopback
                or addr.is_link_local
                or addr.is_reserved
                or addr.is_unspecified
                or addr.is_multicast
            ):
                return False
        return True
    except Exception:
        return False


def _canonical_url(url: str) -> str:
    p = urlparse(url)
    qs = [(k, v) for k, v in parse_qsl(p.query) if not _STRIP_PARAMS.match(k)]
    return urlunparse(p._replace(query=urlencode(qs), fragment=""))


def _manual_job_id(url: str) -> str:
    return "manual:" + hashlib.sha256(_canonical_url(url).encode()).hexdigest()[:12]


@router.get("/matches", response_class=HTMLResponse)
async def matches_list(request: Request) -> HTMLResponse:
    db = request.app.state.db
    config = request.app.state.config
    matches = db.get_all_applications()
    spent = db.sum_costs_this_month()
    sp = request.app.state.search_params_store.load()
    refresh_capped = request.query_params.get("refresh_capped")
    just_saved = request.query_params.get("just_saved")
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
            "just_saved": just_saved,
            "ladder": ladder,
        },
    )


async def start_pipeline_run(request: Request) -> RedirectResponse:
    """Validate guards, kick off a background pipeline run, redirect to progress page."""
    db = request.app.state.db
    config = request.app.state.config
    profile = request.app.state.profile_store.load()
    sp = request.app.state.search_params_store.load()

    if not profile or not sp:
        return RedirectResponse(
            "/wizard/step/1" if not profile else "/wizard/step/3", status_code=303
        )
    if compute_ladder(config, db)["state"] == "gift_exhausted":
        return RedirectResponse("/settings?key_exhausted=1", status_code=303)
    if db.count_runs_today_total() >= config.max_runs_per_day:
        return RedirectResponse("/matches?refresh_capped=1", status_code=303)

    client = request.app.state.client
    run_status = request.app.state.run_status

    for _rid, status in run_status.items():
        if status.get("stage") in ("starting", "scraping", "filtering"):
            return RedirectResponse("/matches?refresh_capped=1", status_code=303)
    run_id = db.start_run()
    run_status[run_id] = {
        "stage": "starting",
        "result": None,
        "error": None,
        "warnings": [],
        "detail": "",
    }

    scrapers: list = [JobSpyScraper(sp)]
    if JooblesScraper.is_configured():
        scrapers.append(JooblesScraper(sp))
    if AdzunaScraper.is_configured():
        scrapers.append(AdzunaScraper(sp))

    if sp.anchor_companies:
        # Probe all three boards for each anchor company in parallel
        all_probes = []
        for c in sp.anchor_companies:
            all_probes.append(asyncio.to_thread(probe_greenhouse, c))
            all_probes.append(asyncio.to_thread(probe_lever, c))
            all_probes.append(asyncio.to_thread(probe_workday, c))
        probe_results = await asyncio.gather(*all_probes, return_exceptions=True)

        gh_skipped: list[str] = []
        for i, company in enumerate(sp.anchor_companies):
            gh_r = probe_results[i * 3]
            lever_r = probe_results[i * 3 + 1]
            workday_r = probe_results[i * 3 + 2]

            # Greenhouse — track skipped for warnings
            if isinstance(gh_r, GreenhouseProbeError):
                logger.warning("Greenhouse probe transient failure: %s", gh_r)
                gh_skipped.append(company)
            elif isinstance(gh_r, Exception):
                logger.warning("Greenhouse probe raised: %s", gh_r)
                gh_skipped.append(company)
            elif gh_r is not None:
                scrapers.append(gh_r)

            # Lever
            if isinstance(lever_r, (LeverProbeError, Exception)):
                logger.warning("Lever probe for %s failed: %s", company, lever_r)
            elif lever_r is not None:
                scrapers.append(lever_r)

            # Workday
            if isinstance(workday_r, (WorkdayProbeError, Exception)):
                logger.warning("Workday probe for %s failed: %s", company, workday_r)
            elif workday_r is not None:
                scrapers.append(workday_r)

        if gh_skipped:
            run_status[run_id]["warnings"].append(
                f"Greenhouse temporarily down — {len(gh_skipped)} target "
                f"compan{'y' if len(gh_skipped) == 1 else 'ies'} skipped"
            )

    def update_stage(stage: str) -> None:
        run_status[run_id]["stage"] = stage

    def update_detail(detail: str, filter_current=0, filter_total=0) -> None:
        run_status[run_id]["detail"] = detail
        if filter_total:
            run_status[run_id]["filter_current"] = filter_current
            run_status[run_id]["filter_total"] = filter_total

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
                update_detail,
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


@router.post("/matches/refresh")
async def refresh_matches(request: Request):
    return await start_pipeline_run(request)


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
            prep_result = json.loads(
                Path(match["interview_prep_path"]).read_text(encoding="utf-8")
            )
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
            "has_full_description": not is_snippet(
                job.get("description"), job.get("source")
            ),
        },
    )


@router.post("/matches/{job_id}/description")
async def update_description(
    job_id: str,
    request: Request,
    description: str = Form(...),
):
    request.app.state.db.update_job_description(job_id, description.strip())
    return RedirectResponse(f"/matches/{job_id}", status_code=303)


@router.post("/matches/{job_id}/description-and-analyze")
async def update_description_and_analyze(
    job_id: str,
    request: Request,
    description: str = Form(...),
):
    db = request.app.state.db
    config = request.app.state.config
    client = request.app.state.client

    db.update_job_description(job_id, description.strip())
    job = db.get_job(job_id)

    if job and compute_ladder(config, db)["state"] != "gift_exhausted":
        profile = request.app.state.profile_store.load()
        if profile:
            try:
                await asyncio.to_thread(
                    ensure_analysis, job, profile, db, config, client=client, force=True
                )
            except Exception as exc:
                logger.error(
                    f"Analysis failed for {job_id} after description update: {exc}"
                )

    return RedirectResponse(f"/matches/{job_id}?open_tailor=1", status_code=303)


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
    db = request.app.state.db
    job = db.get_job(job_id) or {}
    db.dismiss_match(job_id)
    response = HTMLResponse("")
    response.headers["HX-Trigger"] = json.dumps(
        {
            "matchDismissed": {
                "job_id": job_id,
                "company": job.get("company", ""),
                "title": job.get("title", ""),
            }
        }
    )
    return response


@router.post("/matches/{job_id}/undismiss", response_class=HTMLResponse)
async def undismiss_match(job_id: str, request: Request) -> HTMLResponse:
    request.app.state.db.undismiss_match(job_id)
    # Caller bounces back to /matches via the toast Undo handler.
    return HTMLResponse("")


@router.post("/matches/{job_id}/tailor-analyze", response_class=HTMLResponse)
async def tailor_analyze(job_id: str, request: Request) -> HTMLResponse:
    """Run analysis in-modal via HTMX; returns tailor_modal_content partial."""
    db = request.app.state.db
    config = request.app.state.config
    client = request.app.state.client
    templates = request.app.state.templates

    if compute_ladder(config, db)["state"] == "gift_exhausted":
        return HTMLResponse(
            "<div style='padding:20px'><span class='error'>Starter credit used up. "
            "<a href='/settings'>Add your own key →</a></span></div>"
        )

    job = db.get_job(job_id)
    if not job:
        return HTMLResponse(
            "<div style='padding:20px'><span class='error'>Job not found</span></div>"
        )

    profile = request.app.state.profile_store.load()
    if not profile:
        return HTMLResponse(
            "<div style='padding:20px'><span class='error'>Profile not found — "
            "complete onboarding first</span></div>"
        )

    try:
        suggestions = await asyncio.to_thread(
            ensure_analysis, job, profile, db, config, client=client, force=True
        )
    except Exception as exc:
        logger.error(f"tailor-analyze failed for {job_id}: {exc}")
        return HTMLResponse(
            f"<div style='padding:20px'><p class='error'>Analysis failed: {exc}</p>"
            "<div style='padding:12px 0 0'>"
            "<button type='button' class='btn btn-outline btn-sm' "
            "onclick='document.getElementById(\"tailor-modal\").close()'>Close</button>"
            "</div></div>"
        )

    return templates.TemplateResponse(
        request,
        "_partials/tailor_modal_content.html",
        {"suggestions": suggestions, "job": job},
    )


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

    form = await request.form()
    adopt_edits = {
        int(v) for v in form.getlist("edit_index") if str(v).isdigit()
    } or None

    try:
        analysis = await asyncio.to_thread(
            ensure_analysis,
            job,
            profile,
            db,
            config,
            client=client,
        )
        output_dir = config.output_dir / job_id
        result = await asyncio.to_thread(
            run_tailor_for_job,
            job,
            analysis,
            profile,
            output_dir,
            config,
            adopt_edits=adopt_edits,
        )
        rel = Path(result["resume_pdf"]).relative_to(config.output_dir)
        resume_url = f"/output/{rel.as_posix()}"
        db.update_match_paths(job_id, resume_path=resume_url)
        return HTMLResponse(
            f'<a href="{resume_url}" target="_blank" rel="noopener" class="btn btn-success btn-sm">'
            f"✓ Open tailored resume ↗</a>"
        )
    except PdfGenerationError as exc:
        logger.error(f"PDF generation failed for {job_id}: {exc}")
        return HTMLResponse(f"<span class='error'>PDF failed: {exc}</span>")
    except Exception as exc:
        logger.error(f"Tailor failed for {job_id}: {exc}")
        return HTMLResponse(f"<span class='error'>Tailor failed: {exc}</span>")


@router.post("/matches/{job_id}/analyze", response_class=HTMLResponse)
async def analyze_match(job_id: str, request: Request) -> HTMLResponse:
    """Run LLM analysis on-demand; return analysis panels partial."""
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
        force = request.query_params.get("force") == "1"
        if is_snippet(job.get("description"), job.get("source")):
            full_desc = await asyncio.to_thread(fetch_full_description, job["url"])
            if full_desc:
                db.update_job_description(job_id, full_desc)
                job = {**job, "description": full_desc}
                force = True

        suggestions = await asyncio.to_thread(
            ensure_analysis, job, profile, db, config, client=client, force=force
        )
        if request.query_params.get("redirect") == "1":
            return RedirectResponse(f"/matches/{job_id}", status_code=303)
        ladder = compute_ladder(config, db)
        return templates.TemplateResponse(
            request,
            "_partials/analysis_panels.html",
            {"suggestions": suggestions, "job_id": job_id, "ladder": ladder},
        )
    except Exception as exc:
        logger.error(f"Analysis failed for {job_id}: {exc}")
        if request.query_params.get("redirect") == "1":
            return RedirectResponse(f"/matches/{job_id}", status_code=303)
        return HTMLResponse(f"<span class='error'>Analysis failed: {exc}</span>")


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
        if not prep_result:
            return HTMLResponse(
                "<span class='error'>Interview prep failed — please try again.</span>"
            )
        output_dir = config.output_dir / job_id
        output_dir.mkdir(parents=True, exist_ok=True)
        prep_path = output_dir / "interview_prep.json"
        prep_path.write_text(
            json.dumps(prep_result, ensure_ascii=False, indent=2), encoding="utf-8"
        )
        db.update_match_paths(job_id, interview_prep_path=str(prep_path))
        return templates.TemplateResponse(
            request,
            "_partials/interview_prep_result.html",
            {"prep_result": prep_result, "job_id": job_id},
        )
    except Exception as exc:
        logger.error(f"Interview prep failed for {job_id}: {exc}")
        return HTMLResponse(f"<span class='error'>Interview prep failed: {exc}</span>")


@router.get("/matches/{job_id}/interview-prep.pdf")
async def interview_prep_pdf(job_id: str, request: Request):
    """Generate and serve interview-prep PDF on demand."""
    db = request.app.state.db
    config = request.app.state.config

    match = db.get_match(job_id)
    if not match or not match.get("interview_prep_path"):
        return HTMLResponse("Interview prep not found", status_code=404)

    prep_path = Path(match["interview_prep_path"])
    if not prep_path.exists():
        return HTMLResponse("Interview prep data missing", status_code=404)

    try:
        prep_data = json.loads(prep_path.read_text(encoding="utf-8"))
    except Exception:
        return HTMLResponse("Could not read interview prep data", status_code=500)

    job = db.get_job(job_id)
    if not job:
        return HTMLResponse("Job not found", status_code=404)

    try:
        output_dir = config.output_dir / job_id
        pdf_path = await asyncio.to_thread(
            generate_interview_prep_pdf,
            prep_data,
            job.get("title", ""),
            job.get("company", ""),
            output_dir,
            config,
        )
        return FileResponse(
            pdf_path,
            media_type="application/pdf",
            headers={"Content-Disposition": 'inline; filename="interview_prep.pdf"'},
        )
    except PdfGenerationError as exc:
        logger.error(f"Interview prep PDF failed for {job_id}: {exc}")
        return HTMLResponse(f"PDF generation failed: {exc}", status_code=500)


@router.post("/matches/add-company", response_class=HTMLResponse)
async def add_company(request: Request, company: str = Form(...)) -> HTMLResponse:
    """Probe job boards for a company; if found, launch a background scrape+filter."""
    company = company.strip()
    if not company:
        return HTMLResponse(
            "<div class='alert alert-error' style='margin:0 0 8px;padding:8px 12px;font-size:13px'>"
            "Please enter a company name.</div>"
        )

    db = request.app.state.db
    config = request.app.state.config
    client = request.app.state.client
    profile = request.app.state.profile_store.load()
    sp = request.app.state.search_params_store.load()

    if not profile or not sp:
        return HTMLResponse(
            "<div class='alert alert-error' style='margin:0 0 8px;padding:8px 12px;font-size:13px'>"
            "Complete onboarding before adding companies.</div>"
        )
    if compute_ladder(config, db)["state"] == "gift_exhausted":
        return HTMLResponse(
            "<div class='alert alert-error' style='margin:0 0 8px;padding:8px 12px;font-size:13px'>"
            "Starter credit used up. <a href='/settings'>Add your own key →</a></div>"
        )
    if client is None:
        return HTMLResponse(
            "<div class='alert alert-error' style='margin:0 0 8px;padding:8px 12px;font-size:13px'>"
            "No API key configured. <a href='/settings'>Add one →</a></div>"
        )

    # Concurrency guard — only one pipeline at a time
    run_status = request.app.state.run_status
    for _rid, status in run_status.items():
        if status.get("stage") in ("starting", "scraping", "filtering"):
            return HTMLResponse(
                "<div class='alert alert-error' style='margin:0 0 8px;padding:8px 12px;font-size:13px'>"
                "A scan is already running — wait for it to finish.</div>"
            )

    # Probe all supported job boards in parallel
    probe_results = await asyncio.gather(
        asyncio.to_thread(probe_greenhouse, company),
        asyncio.to_thread(probe_lever, company),
        asyncio.to_thread(probe_workday, company),
        return_exceptions=True,
    )

    scraper = None
    all_transient = all(isinstance(r, Exception) for r in probe_results)
    if not all_transient:
        for r in probe_results:
            if not isinstance(r, Exception) and r is not None:
                scraper = r
                break

    if scraper is None and all_transient:
        return HTMLResponse(
            "<div class='alert alert-error' style='margin:0 0 8px;padding:8px 12px;font-size:13px'>"
            "Job board services temporarily unreachable — try again in a minute.</div>"
        )

    if scraper is None:
        return HTMLResponse(
            "<div class='alert alert-error' style='margin:0 0 8px;padding:8px 12px;font-size:13px'>"
            f"No public job board found for '{html_mod.escape(company)}'.</div>"
        )

    # Launch background pipeline for this single company
    run_id = db.start_run(kind="add_company")
    run_status[run_id] = {
        "stage": "starting",
        "result": None,
        "error": None,
        "warnings": [],
        "detail": "",
        "filter_current": 0,
        "filter_total": 0,
        "company": company,
    }

    search_params_store = request.app.state.search_params_store

    def update_stage(stage: str) -> None:
        run_status[run_id]["stage"] = stage

    def update_detail(detail: str, filter_current=0, filter_total=0) -> None:
        run_status[run_id]["detail"] = detail
        if filter_total:
            run_status[run_id]["filter_current"] = filter_current
            run_status[run_id]["filter_total"] = filter_total

    async def _run():
        try:
            result = await asyncio.to_thread(
                run_pipeline,
                db,
                profile,
                sp,
                config,
                [scraper],
                client,
                run_id,
                update_stage,
                update_detail,
            )
            search_params_store.add_anchor_company(company)
            run_status[run_id]["stage"] = "done"
            run_status[run_id]["result"] = result
        except Exception as exc:
            logger.error(f"Add-company pipeline run {run_id} failed: {exc}")
            run_status[run_id]["stage"] = "error"
            run_status[run_id]["error"] = str(exc)

    task = asyncio.create_task(_run())
    background_tasks = request.app.state.background_tasks
    background_tasks.add(task)
    task.add_done_callback(background_tasks.discard)

    response = HTMLResponse(
        "<div class='alert alert-info' style='margin:0 0 8px;padding:8px 12px;font-size:13px'>"
        "Scanning — check progress below.</div>"
    )
    response.headers["HX-Trigger"] = json.dumps(
        {"addCompanyStarted": {"run_id": run_id, "company": company}}
    )
    return response


@router.post("/matches/add-job")
async def add_job(
    request: Request,
    url: str = Form(...),
    title: str = Form(...),
    company: str = Form(...),
    location: str = Form(""),
    salary: str = Form(""),
    remote: str = Form(""),
    description: str = Form(""),
):
    url = url.strip()
    if not _is_safe_url(url):
        # B6.3: HTMX form swaps this fragment into #add-job-result so the
        # modal stays open with the user's typed values intact.
        return HTMLResponse(
            "<div class='alert alert-error' style='margin:0 0 8px;padding:8px 12px;font-size:13px'>"
            "Invalid URL — must be a public http(s) link.</div>"
        )
    db = request.app.state.db
    config = request.app.state.config
    client = request.app.state.client
    clean_description = description.strip() or None

    job_id = _manual_job_id(url)
    db.add_manual_job(
        job_id=job_id,
        url=url,
        title=title.strip(),
        company=company.strip(),
        location=location.strip() or None,
        salary=salary.strip() or None,
        remote=remote == "on",
        description=clean_description,
    )

    # Auto-analyze when description provided and budget allows
    redirect_url = f"/matches/{job_id}"
    if clean_description and compute_ladder(config, db)["state"] != "gift_exhausted":
        profile = request.app.state.profile_store.load()
        if profile:
            job = db.get_job(job_id)
            try:
                await asyncio.to_thread(
                    ensure_analysis, job, profile, db, config, client=client, force=True
                )
                redirect_url = f"/matches/{job_id}?open_tailor=1"
            except Exception as exc:
                logger.error(f"Analysis failed for manually added job {job_id}: {exc}")

    # HTMX-aware: when the request came from the in-page form, ask the
    # client to navigate via HX-Redirect instead of a 303 (the form was
    # swapping into a fragment slot, so a Location redirect would be
    # ignored).
    if request.headers.get("HX-Request") == "true":
        response = HTMLResponse("")
        response.headers["HX-Redirect"] = redirect_url
        return response
    return RedirectResponse(redirect_url, status_code=303)


@router.get("/output/{path:path}")
async def serve_output_file(path: str, request: Request):
    """Serve files from the output directory (tailored resumes, interview prep)."""
    output_dir = request.app.state.config.output_dir.resolve()
    file_path = (output_dir / path).resolve()
    if not str(file_path).startswith(str(output_dir)):
        return HTMLResponse("Forbidden", status_code=403)
    if not file_path.exists():
        return HTMLResponse("Not found", status_code=404)
    return FileResponse(file_path)
