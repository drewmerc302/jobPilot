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
    has_key = bool(key.strip())
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
            "has_key": has_key,
            "monthly_budget": config.monthly_budget,
            "total_budget": config.total_budget,
            "saved": request.query_params.get("saved") == "1",
            "cleared": request.query_params.get("cleared") == "1",
            "key_exhausted": request.query_params.get("key_exhausted") == "1",
            "missing_adzuna": request.query_params.get("missing_adzuna") == "1",
        },
    )


@router.post("/settings", response_class=HTMLResponse)
async def settings_post(
    request: Request,
    api_key: str = Form(default=""),
    monthly_budget: float = Form(default=5.0),
    total_budget: float = Form(default=10.0),
) -> HTMLResponse:
    config = request.app.state.config

    monthly_budget = max(0.5, min(50.0, monthly_budget))
    total_budget = max(5.0, min(50.0, total_budget))

    overrides: dict = {
        "monthly_budget": monthly_budget,
        "total_budget": total_budget,
    }
    if api_key.strip():
        overrides["anthropic_api_key"] = api_key.strip()
        overrides["has_byo_key"] = True

    config.save_overrides(**overrides)

    config.monthly_budget = monthly_budget
    config.total_budget = total_budget
    if api_key.strip():
        config.anthropic_api_key = api_key.strip()
        config.has_byo_key = True
        request.app.state.client = anthropic.Anthropic(
            api_key=config.anthropic_api_key, timeout=90
        )

    return RedirectResponse("/settings?saved=1", status_code=303)


@router.post("/settings/clear-key")
async def settings_clear_key(request: Request) -> RedirectResponse:
    """Wipe the saved Anthropic key and revert to gift-credit mode."""
    config = request.app.state.config
    overrides_path = config.data_dir / "config_overrides.json"
    existing: dict = {}
    if overrides_path.exists():
        try:
            import json as _json

            existing = _json.loads(overrides_path.read_text())
        except Exception:
            existing = {}
    existing["anthropic_api_key"] = ""
    existing["has_byo_key"] = False
    tmp = overrides_path.with_suffix(".tmp")
    tmp.parent.mkdir(parents=True, exist_ok=True)
    import json as _json

    tmp.write_text(_json.dumps(existing, ensure_ascii=False, indent=2))
    tmp.replace(overrides_path)

    config.anthropic_api_key = ""
    config.has_byo_key = False
    request.app.state.client = None

    return RedirectResponse("/settings?cleared=1", status_code=303)
