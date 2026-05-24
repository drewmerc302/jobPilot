"""Polling and utility API endpoints (HTMX fragments only — no JSON)."""

import html
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
    warnings: list[str] = []

    # Determine stage from in-memory dict first, fall back to DB column.
    # If the row is gone entirely, mark unknown — the partial renders an
    # actionable "start a new search" message instead of a poll loop.
    if progress is not None:
        stage = progress.get("stage", "starting")
        result = progress.get("result")
        error = progress.get("error")
        warnings = list(progress.get("warnings") or [])
    elif run:
        # B2.2: surfaced when the app was killed mid-run; _migrate stamps
        # error='App crashed' on any run with completed_at IS NULL at
        # startup, so the polling page shows a real recovery message.
        if (run.get("error") or "").lower() == "app crashed":
            stage = "crashed"
            result = None
            error = run.get("error")
        else:
            stage = run.get("current_stage") or (
                "done" if run.get("completed_at") else "starting"
            )
            result = None
            error = run.get("error")
    else:
        stage = "unknown"
        result = None
        error = None

    detail = (progress or {}).get("detail", "")
    filter_current = (progress or {}).get("filter_current", 0)
    filter_total = (progress or {}).get("filter_total", 0)

    ctx = {
        "run_id": run_id,
        "stage": stage,
        "run": run,
        "result": result,
        "error": error,
        "warnings": warnings,
        "detail": detail,
        "filter_current": filter_current,
        "filter_total": filter_total,
        "company": (progress or {}).get("company", ""),
    }

    compact = request.query_params.get("compact") == "1"
    template_name = (
        "_partials/add_company_status.html" if compact else "_partials/run_status.html"
    )

    if stage in ("starting", "scraping", "filtering"):
        return templates.TemplateResponse(request, template_name, ctx)

    if stage == "done":
        config = request.app.state.config
        spent = db.sum_costs_this_month()
        ctx["spent"] = spent
        ctx["budget"] = config.monthly_budget
        response = templates.TemplateResponse(request, template_name, ctx)
        remaining = max(0.0, config.total_budget - db.sum_costs_total())
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
                "remaining": remaining,
            }
        }
        response.headers["HX-Trigger"] = json.dumps(trigger_data)
        return response

    # error or unknown
    return templates.TemplateResponse(request, template_name, ctx)


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
async def test_key(request: Request, api_key: str = Form(default="")) -> HTMLResponse:
    """Validate an Anthropic API key with a minimal call.

    If the form field is blank, fall through to the stored key (so the user
    can verify the key already saved without retyping it).
    """
    key = (api_key or "").strip()
    using_saved = False
    if not key:
        stored = (request.app.state.config.anthropic_api_key or "").strip()
        if not stored:
            return HTMLResponse(
                "<span class='error'>No saved key — paste one to test.</span>"
            )
        key = stored
        using_saved = True
    try:
        client = anthropic.Anthropic(api_key=key, timeout=10)
        client.messages.create(
            model="claude-haiku-4-5-20251001",
            max_tokens=1,
            messages=[{"role": "user", "content": "hi"}],
        )
        label = "saved key" if using_saved else "key"
        return HTMLResponse(
            f"<span style='color:var(--green);font-size:13px'>✓ {label.capitalize()} is valid</span>"
        )
    except anthropic.AuthenticationError:
        return HTMLResponse("<span class='error'>✗ Invalid key</span>")
    except Exception as exc:
        logger.warning(f"test-key failed: {exc}")
        return HTMLResponse(f"<span class='error'>✗ {html.escape(str(exc))}</span>")
