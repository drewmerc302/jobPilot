"""Settings page: API key and monthly budget management."""

import logging

import anthropic
from fastapi import APIRouter, Form, Request
from fastapi.responses import HTMLResponse, RedirectResponse

logger = logging.getLogger(__name__)
router = APIRouter()


@router.get("/settings", response_class=HTMLResponse)
async def settings_get(request: Request) -> HTMLResponse:
    config = request.app.state.config
    key = config.anthropic_api_key or ""
    key_hint = (
        f"••••••••••••{key[-4:]}"
        if len(key) > 4
        else ("(not set)" if not key else "••••")
    )
    return request.app.state.templates.TemplateResponse(
        request,
        "settings.html",
        {
            "key_hint": key_hint,
            "monthly_budget": config.monthly_budget,
            "saved": request.query_params.get("saved") == "1",
            "key_exhausted": request.query_params.get("key_exhausted") == "1",
        },
    )


@router.post("/settings", response_class=HTMLResponse)
async def settings_post(
    request: Request,
    api_key: str = Form(default=""),
    monthly_budget: float = Form(default=5.0),
) -> HTMLResponse:
    config = request.app.state.config

    monthly_budget = max(0.5, min(50.0, monthly_budget))

    overrides: dict = {"monthly_budget": monthly_budget}
    if api_key.strip():
        overrides["anthropic_api_key"] = api_key.strip()
        overrides["has_byo_key"] = True

    config.save_overrides(**overrides)

    config.monthly_budget = monthly_budget
    if api_key.strip():
        config.anthropic_api_key = api_key.strip()
        config.has_byo_key = True
        request.app.state.client = anthropic.Anthropic(api_key=config.anthropic_api_key)

    return RedirectResponse("/settings?saved=1", status_code=303)
