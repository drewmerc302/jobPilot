"""Edit-search routes: diff preview and save."""

import logging

from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse, RedirectResponse

from jobpilot.search_params import SearchParams

logger = logging.getLogger(__name__)
router = APIRouter()

_REFRAME_FIELDS = {"keywords", "location"}


def _parse_form_to_params(form) -> SearchParams:
    keywords = [k.strip() for k in form.get("keywords", "").split(",") if k.strip()]
    anchor_companies = [
        a.strip() for a in form.get("anchor_companies", "").splitlines() if a.strip()
    ]
    return SearchParams(
        keywords=keywords,
        location=form.get("location", ""),
        radius_miles=int(form.get("radius_miles", 25)),
        remote_ok=form.get("remote_ok") == "on",
        seniority=form.get("seniority") or None,
        anchor_companies=anchor_companies,
    )


def _classify(old: SearchParams | None, new: SearchParams) -> str:
    """Return 'tweak' or 'reframe'."""
    if old is None:
        return "reframe"
    if set(new.keywords) != set(old.keywords):
        return "reframe"
    if new.location.strip().lower() != old.location.strip().lower():
        return "reframe"
    return "tweak"


@router.post("/search-params/preview", response_class=HTMLResponse)
async def search_params_preview(request: Request) -> HTMLResponse:
    form = await request.form()
    old = request.app.state.search_params_store.load()
    new = _parse_form_to_params(form)
    category = _classify(old, new)

    templates = request.app.state.templates
    db = request.app.state.db

    match_count = len(db.get_all_applications()) if category == "reframe" else 0
    cost_estimate = round(match_count * 0.001, 2)

    return templates.TemplateResponse(
        "_partials/search_diff_preview.html",
        {
            "request": request,
            "category": category,
            "match_count": match_count,
            "cost_estimate": cost_estimate,
        },
    )


@router.post("/search-params/save", response_class=HTMLResponse)
async def search_params_save(request: Request) -> HTMLResponse:
    form = await request.form()
    new = _parse_form_to_params(form)
    request.app.state.search_params_store.save(new)
    return RedirectResponse("/matches", status_code=303)
