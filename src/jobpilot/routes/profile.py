"""Resume profile editor — view and update the stored profile.json."""

import asyncio
import html as _html
import json
import logging

import anthropic
from fastapi import APIRouter, Request
from fastapi.responses import FileResponse, HTMLResponse, RedirectResponse

import jobpilot.llm as llm
from jobpilot.config import Config

logger = logging.getLogger(__name__)
router = APIRouter()

# ---------------------------------------------------------------------------
# LLM tool schemas
# ---------------------------------------------------------------------------

_SUGGEST_SUMMARY_TOOL = {
    "name": "suggest_summary",
    "description": "Write an improved professional summary",
    "input_schema": {
        "type": "object",
        "properties": {
            "summary": {
                "type": "string",
                "description": "Improved professional summary, 2-5 sentences. Start with a strong noun or verb phrase, omit 'I'.",
            }
        },
        "required": ["summary"],
    },
}

_PARSE_EXPERIENCE_TOOL = {
    "name": "parse_experience",
    "description": "Parse freeform work experience text into structured format",
    "input_schema": {
        "type": "object",
        "properties": {
            "company": {"type": "string"},
            "location": {"type": "string"},
            "positions": {
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": {
                        "title": {"type": "string"},
                        "dates": {"type": "string"},
                        "achievements": {
                            "type": "array",
                            "items": {"type": "string"},
                        },
                    },
                    "required": ["title", "dates", "achievements"],
                },
            },
        },
        "required": ["company", "positions"],
    },
}

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _skills_to_text(skills: dict) -> str:
    lines = []
    for items in (skills or {}).values():
        if isinstance(items, list):
            lines.extend(str(s) for s in items if s)
    return "\n".join(lines)


def _text_to_skills(text: str) -> dict:
    items = [ln.strip() for ln in text.splitlines() if ln.strip()]
    return {"Skills": items} if items else {}


def _parse_experience_from_form(form) -> list[dict]:
    experience = []
    i = 0
    while True:
        company = (form.get(f"exp_{i}_company") or "").strip()
        if not company:
            break
        location = (form.get(f"exp_{i}_location") or "").strip()
        positions = []
        j = 0
        while True:
            title = (form.get(f"exp_{i}_pos_{j}_title") or "").strip()
            if not title:
                break
            dates = (form.get(f"exp_{i}_pos_{j}_dates") or "").strip()
            raw = form.get(f"exp_{i}_pos_{j}_achievements") or ""
            achievements = [
                ln.strip().lstrip("•–- ").strip()
                for ln in raw.splitlines()
                if ln.strip()
            ]
            positions.append(
                {"title": title, "dates": dates, "achievements": achievements}
            )
            j += 1
        entry: dict = {"company": company, "positions": positions}
        if location:
            entry["location"] = location
        experience.append(entry)
        i += 1
    return experience


def _parse_education_from_form(form) -> list[dict]:
    education = []
    k = 0
    while True:
        institution = (form.get(f"edu_{k}_institution") or "").strip()
        if not institution:
            break
        entry: dict = {
            "institution": institution,
            "degree": (form.get(f"edu_{k}_degree") or "").strip(),
        }
        for opt in ["graduation_year", "location", "gpa", "honors"]:
            val = (form.get(f"edu_{k}_{opt}") or "").strip()
            if val:
                entry[opt] = val
        education.append(entry)
        k += 1
    return education


_RATING_LABELS = {
    "strong": ("✓", "var(--green)", "Strong"),
    "weak_no_metric": ("⚠", "#d97706", "No metric"),
    "weak_no_outcome": ("⚠", "#d97706", "No outcome"),
    "weak_passive_verb": ("⚠", "#d97706", "Passive verb"),
    "vague": ("⚠", "#9333ea", "Vague"),
}


def _render_bullet_analysis(profile: dict, scores: dict) -> str:
    """Render the bullet analysis panel HTML."""
    if not scores:
        return "<p class='muted' style='font-size:13px;padding:8px 0'>No bullets to score.</p>"

    weak_bullets = [
        (key, data) for key, data in scores.items() if data["rating"] != "strong"
    ]
    strong_count = sum(1 for d in scores.values() if d["rating"] == "strong")
    total = len(scores)

    if not weak_bullets:
        return (
            f"<div style='color:var(--green);font-size:13px;padding:8px 0'>"
            f"✓ All {total} bullets look strong.</div>"
        )

    # Build lookup: key → bullet text + context
    bullet_lookup: dict[str, dict] = {}
    for exp_idx, exp in enumerate(profile.get("experience") or []):
        for pos_idx, pos in enumerate(exp.get("positions") or []):
            for bullet_idx, bullet in enumerate(pos.get("achievements") or []):
                key = f"{exp_idx}-{pos_idx}-{bullet_idx}"
                bullet_lookup[key] = {
                    "text": bullet.strip(),
                    "context": f"{exp.get('company', '')} — {pos.get('title', '')}",
                    "exp_idx": exp_idx,
                    "pos_idx": pos_idx,
                    "bullet_idx": bullet_idx,
                }

    rows = []
    for key, score_data in weak_bullets:
        info = bullet_lookup.get(key)
        if not info:
            continue
        rating = score_data["rating"]
        note = score_data.get("note", "")
        icon, color, label = _RATING_LABELS.get(rating, ("⚠", "#d97706", rating))
        safe_text = _html.escape(info["text"])
        safe_context = _html.escape(info["context"])
        safe_note = _html.escape(note)
        ei, pi, bi = info["exp_idx"], info["pos_idx"], info["bullet_idx"]
        ta_name = f"exp_{ei}_pos_{pi}_achievements"
        improve_target = f"improve-slot-{key.replace('-', '_')}"

        # Build hx-vals as proper JSON, then html-escape so it survives any
        # special chars (apostrophes, quotes) in bullet text or ta_name.
        hx_vals = _html.escape(
            json.dumps(
                {
                    "exp_idx": str(ei),
                    "pos_idx": str(pi),
                    "bullet_idx": str(bi),
                    "bullet_text": info["text"],
                    "rating": rating,
                    "ta_name": ta_name,
                }
            ),
            quote=True,
        )

        rows.append(f"""
<div style="border:1px solid var(--border);border-radius:var(--radius);padding:12px;margin-bottom:10px">
  <div style="font-size:11px;font-weight:700;text-transform:uppercase;letter-spacing:.5px;color:var(--muted);margin-bottom:4px">{safe_context}</div>
  <div style="display:flex;align-items:flex-start;gap:8px;margin-bottom:8px">
    <span style="color:{color};font-weight:700;flex-shrink:0">{icon}</span>
    <span style="font-size:13px;line-height:1.5">{safe_text}</span>
  </div>
  <div style="display:flex;align-items:center;gap:8px;flex-wrap:wrap">
    <span style="font-size:11px;color:{color};font-weight:600;background:{color}18;padding:2px 7px;border-radius:10px">{label}</span>
    {f'<span class="muted" style="font-size:11px">{safe_note}</span>' if note else ""}
    <button type="button" class="btn btn-outline btn-sm"
            style="margin-left:auto"
            hx-post="/profile/improve-bullet"
            hx-target="#{_html.escape(improve_target)}"
            hx-swap="innerHTML"
            hx-vals="{hx_vals}"
            onclick="this.disabled=true;this.textContent='Loading…'"
            hx-on::after-request="this.disabled=false;this.textContent='✦ Improve'">
      ✦ Improve
    </button>
  </div>
  <div id="{_html.escape(improve_target)}"></div>
</div>""")

    header = (
        f"<div style='font-size:13px;margin-bottom:12px'>"
        f"<strong>{len(weak_bullets)}</strong> of {total} bullets need work &nbsp;·&nbsp; "
        f"<span style='color:var(--green)'>{strong_count} strong</span>"
        f"</div>"
    )
    return header + "\n".join(rows)


# ---------------------------------------------------------------------------
# LLM calls (sync, run in thread)
# ---------------------------------------------------------------------------


def _llm_suggest_summary(
    current_summary: str,
    accomplishments: str,
    client: anthropic.Anthropic,
    config: Config,
    db,
) -> str:
    parts = []
    if current_summary:
        parts.append(f"Current summary:\n{current_summary}")
    parts.append(
        f"Recent accomplishments and strengths the person wants to highlight:\n{accomplishments}"
    )
    parts.append(
        "Write an improved professional summary of 2-5 sentences. "
        "Start with a strong noun or verb phrase — omit 'I'. "
        "Be specific and concrete; prefer numbers and outcomes over adjectives."
    )
    response = llm.call(
        client,
        db,
        "profile_suggest_summary",
        model=config.llm_tailor_model,
        max_tokens=512,
        tools=[_SUGGEST_SUMMARY_TOOL],
        tool_choice={"type": "tool", "name": "suggest_summary"},
        messages=[{"role": "user", "content": "\n\n".join(parts)}],
    )
    for block in response.content:
        if block.type == "tool_use":
            return block.input.get("summary", "")
    return ""


def _llm_parse_experience(
    text: str,
    client: anthropic.Anthropic,
    config: Config,
    db,
) -> dict | None:
    response = llm.call(
        client,
        db,
        "profile_parse_experience",
        model=config.llm_extract_model,
        max_tokens=1024,
        tools=[_PARSE_EXPERIENCE_TOOL],
        tool_choice={"type": "tool", "name": "parse_experience"},
        messages=[
            {
                "role": "user",
                "content": (
                    "Parse this work experience description into structured format. "
                    "Convert narrative text into concise achievement bullet points starting with strong action verbs. "
                    "If dates aren't mentioned, use an empty string.\n\n"
                    f"{text}"
                ),
            }
        ],
    )
    for block in response.content:
        if block.type == "tool_use":
            return block.input
    return None


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------


@router.get("/profile", response_class=HTMLResponse)
async def profile_get(request: Request) -> HTMLResponse:
    profile = request.app.state.profile_store.load() or {}
    bullet_analysis_html = ""
    if profile.get("bullet_scores") is not None:
        bullet_analysis_html = _render_bullet_analysis(
            profile, profile["bullet_scores"]
        )
    return request.app.state.templates.TemplateResponse(
        request,
        "profile_edit.html",
        {
            "profile": profile,
            "skills_text": _skills_to_text(profile.get("skills") or {}),
            "saved": request.query_params.get("saved") == "1",
            "bullet_analysis_html": bullet_analysis_html,
        },
    )


@router.post("/profile/save")
async def profile_save(request: Request):
    profile_store = request.app.state.profile_store
    profile = profile_store.load() or {}
    form = await request.form()

    # Contact fields stored flat at profile root
    for field in [
        "name",
        "title",
        "email",
        "phone",
        "location",
        "linkedin",
        "github",
        "website",
    ]:
        profile[field] = (form.get(field) or "").strip()

    profile["summary"] = (form.get("summary") or "").strip()
    profile["skills"] = _text_to_skills(form.get("skills_text") or "")
    experience = _parse_experience_from_form(form)

    # Optional: add new experience via LLM parse
    new_exp_text = (form.get("new_experience") or "").strip()
    if new_exp_text:
        try:
            parsed = await asyncio.to_thread(
                _llm_parse_experience,
                new_exp_text,
                request.app.state.client,
                request.app.state.config,
                request.app.state.db,
            )
            if parsed:
                experience.append(parsed)
        except Exception as exc:
            logger.warning(f"New experience parse failed: {exc}")

    profile["experience"] = experience
    profile.pop(
        "bullet_scores", None
    )  # scores are positional; stale after any experience edit
    # B7.1: only overwrite education when the form posted at least one
    # institution. Otherwise the user opened the page without touching
    # the section and we'd silently nuke their stored entries.
    parsed_education = _parse_education_from_form(form)
    if parsed_education:
        profile["education"] = parsed_education
    elif "education" not in profile:
        profile["education"] = []
    profile["low_confidence_fields"] = []
    profile_store.save(profile)
    return RedirectResponse("/profile?saved=1", status_code=303)


@router.post("/profile/suggest-summary", response_class=HTMLResponse)
async def suggest_summary(request: Request) -> HTMLResponse:
    form = await request.form()
    current_summary = (form.get("summary") or "").strip()
    accomplishments = (form.get("accomplishments") or "").strip()

    if not accomplishments:
        return HTMLResponse(
            "<p class='muted' style='font-size:13px;margin:4px 0 0'>Describe your accomplishments first.</p>"
        )

    try:
        suggested = await asyncio.to_thread(
            _llm_suggest_summary,
            current_summary,
            accomplishments,
            request.app.state.client,
            request.app.state.config,
            request.app.state.db,
        )
    except Exception as exc:
        logger.warning(f"Summary suggestion failed: {exc}")
        return HTMLResponse(
            "<p class='muted' style='font-size:13px;margin:4px 0 0'>Suggestion failed — please try again.</p>"
        )

    safe_html = _html.escape(suggested)
    js_str = json.dumps(suggested)  # valid JS string literal, properly escaped
    return HTMLResponse(f"""
<div style="background:#f0f7ff;border:1px solid #b8d4f0;border-radius:6px;padding:14px;margin-top:10px">
  <p style="margin:0 0 4px;font-size:11px;font-weight:700;text-transform:uppercase;letter-spacing:.5px;color:var(--muted)">Suggested</p>
  <p style="margin:0 0 12px;font-size:14px;line-height:1.6">{safe_html}</p>
  <button type="button" class="btn btn-primary btn-sm"
          onclick="document.getElementById('summary-textarea').value={js_str};document.getElementById('summary-suggestion').innerHTML=''">
    Use this
  </button>
  <button type="button" class="btn btn-outline btn-sm" style="margin-left:6px"
          onclick="document.getElementById('summary-suggestion').innerHTML=''">
    Discard
  </button>
</div>
""")


@router.post("/profile/score-bullets", response_class=HTMLResponse)
async def score_bullets_route(request: Request) -> HTMLResponse:
    from jobpilot.steps.bullet_scorer import score_bullets

    profile_store = request.app.state.profile_store
    profile = profile_store.load() or {}

    if not profile.get("experience"):
        return HTMLResponse(
            "<p class='muted' style='font-size:13px'>No experience entries to analyze.</p>"
        )

    try:
        scores = await asyncio.to_thread(
            score_bullets,
            profile,
            request.app.state.client,
            request.app.state.config,
            request.app.state.db,
        )
    except Exception as exc:
        logger.warning(f"Bullet scoring failed: {exc}")
        return HTMLResponse(
            "<p class='muted' style='font-size:13px'>Scoring failed — please try again.</p>"
        )

    profile["bullet_scores"] = scores
    profile_store.save(profile)
    return HTMLResponse(_render_bullet_analysis(profile, scores))


@router.get("/profile/generate-pdf")
async def profile_generate_pdf(request: Request):
    from jobpilot.steps.tailor import generate_resume_pdf

    profile = request.app.state.profile_store.load() or {}
    if not profile:
        return HTMLResponse("No profile found. Complete setup first.", status_code=400)

    output_dir = request.app.state.config.output_dir / "base_resume"
    pdf_path = await asyncio.to_thread(
        generate_resume_pdf,
        profile,
        output_dir,
        request.app.state.config,
    )

    if not pdf_path or not pdf_path.exists():
        return HTMLResponse(
            "PDF generation failed — Typst binary may be missing.", status_code=500
        )

    return FileResponse(
        pdf_path,
        media_type="application/pdf",
        headers={"Content-Disposition": 'inline; filename="resume.pdf"'},
    )
