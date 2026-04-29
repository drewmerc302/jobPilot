"""Polling and utility API endpoints (HTMX fragments only — no JSON)."""

import json
import logging

from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse

logger = logging.getLogger(__name__)
router = APIRouter()


@router.get("/api/run/{run_id}/status", response_class=HTMLResponse)
async def run_status(run_id: int, request: Request) -> HTMLResponse:
    """HTMX polling target. Returns HTML partial.

    While running: partial re-embeds hx-trigger="every 1s" (keeps polling).
    On complete: partial omits hx-trigger (polling stops) and sets HX-Trigger
    header so the client can refresh the cost meter and show a toast.
    """
    db = request.app.state.db
    templates = request.app.state.templates
    run_status_dict = request.app.state.run_status

    progress = run_status_dict.get(run_id)
    run = db.get_run(run_id)

    # Determine stage from in-memory dict first, fall back to DB column
    if progress is not None:
        stage = progress.get("stage", "starting")
        result = progress.get("result")
        error = progress.get("error")
    elif run:
        stage = run.get("current_stage") or (
            "done" if run.get("completed_at") else "starting"
        )
        result = None
        error = run.get("error")
    else:
        stage = "unknown"
        result = None
        error = None

    ctx = {
        "request": request,
        "run_id": run_id,
        "stage": stage,
        "run": run,
        "result": result,
        "error": error,
    }

    if stage in ("starting", "scraping", "filtering"):
        return templates.TemplateResponse("_partials/run_status.html", ctx)

    if stage == "done":
        config = request.app.state.config
        spent = db.sum_costs_this_month()
        ctx["spent"] = spent
        ctx["budget"] = config.monthly_budget
        response = templates.TemplateResponse("_partials/run_status.html", ctx)
        trigger_data = {
            "runComplete": {
                "run_id": run_id,
                "new_matches": (result or {}).get(
                    "new_matches", run.get("matches_found", 0) if run else 0
                ),
                "new_jobs": (result or {}).get(
                    "new_jobs", run.get("new_jobs", 0) if run else 0
                ),
                "spent": spent,
            }
        }
        response.headers["HX-Trigger"] = json.dumps(trigger_data)
        return response

    # error or unknown
    return templates.TemplateResponse("_partials/run_status.html", ctx)


@router.get("/api/cost/meter", response_class=HTMLResponse)
async def cost_meter(request: Request) -> HTMLResponse:
    db = request.app.state.db
    config = request.app.state.config
    templates = request.app.state.templates
    spent = db.sum_costs_this_month()
    return templates.TemplateResponse(
        "_partials/cost_meter.html",
        {"request": request, "spent": spent, "budget": config.monthly_budget},
    )
