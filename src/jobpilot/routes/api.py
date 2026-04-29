"""Polling and utility API endpoints (HTMX fragments only — no JSON)."""

import json
import logging

import anthropic
from fastapi import APIRouter, Form, Request
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
        "run_id": run_id,
        "stage": stage,
        "run": run,
        "result": result,
        "error": error,
    }

    if stage in ("starting", "scraping", "filtering"):
        return templates.TemplateResponse(request, "_partials/run_status.html", ctx)

    if stage == "done":
        config = request.app.state.config
        spent = db.sum_costs_this_month()
        ctx["spent"] = spent
        ctx["budget"] = config.monthly_budget
        response = templates.TemplateResponse(request, "_partials/run_status.html", ctx)
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
    return templates.TemplateResponse(request, "_partials/run_status.html", ctx)


@router.get("/api/cost/meter", response_class=HTMLResponse)
async def cost_meter(request: Request) -> HTMLResponse:
    db = request.app.state.db
    config = request.app.state.config
    templates = request.app.state.templates
    spent = db.sum_costs_this_month()
    return templates.TemplateResponse(
        request,
        "_partials/cost_meter.html",
        {"spent": spent, "budget": config.monthly_budget},
    )


@router.post("/api/test-key", response_class=HTMLResponse)
async def test_key(api_key: str = Form(...)) -> HTMLResponse:
    """Validate an Anthropic API key with a minimal call. Returns an inline status span."""
    key = api_key.strip()
    if not key:
        return HTMLResponse("<span class='error'>Enter a key to test.</span>")
    try:
        client = anthropic.Anthropic(api_key=key)
        client.messages.create(
            model="claude-haiku-4-5-20251001",
            max_tokens=1,
            messages=[{"role": "user", "content": "hi"}],
        )
        return HTMLResponse(
            "<span style='color:var(--green);font-size:13px'>✓ Key is valid</span>"
        )
    except anthropic.AuthenticationError:
        return HTMLResponse("<span class='error'>✗ Invalid key</span>")
    except Exception as exc:
        logger.warning(f"test-key failed: {exc}")
        return HTMLResponse(f"<span class='error'>✗ {exc}</span>")
