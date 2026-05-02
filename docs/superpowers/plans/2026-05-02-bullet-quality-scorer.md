# Bullet Quality Scorer & Improver Implementation Plan

> **For agentic workers:** REQUIRED: Use superpowers-extended-cc:subagent-driven-development (if subagents available) or superpowers-extended-cc:executing-plans to implement this plan. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add per-bullet quality scoring and inline AI-assisted improvement to the master profile's Experience section, so every tailoring run starts from stronger raw material.

**Architecture:** A new `bullet_scorer.py` step runs the LLM scan and returns a scores dict keyed by `exp_idx-pos_idx-bullet_idx`. Scores persist in `profile.json` under `bullet_scores`. Three new HTMX endpoints in `routes/profile.py` handle (1) scoring, (2) targeted follow-up questions, and (3) rewrite suggestions. The UI renders a read-only analysis panel below the Experience card; scores from the last run are server-rendered on GET /profile. A fire-and-forget async task in the wizard auto-scores on first upload. Stale scores are cleared whenever the experience array is rewritten on profile save.

**Tech Stack:** Python/FastAPI, HTMX (already vendored), Anthropic tool-use (same `llm.call` wrapper), Jinja2 templates, pytest (no LLM calls in tests — pure unit tests only)

---

## File Map

| Action | Path | Responsibility |
|--------|------|----------------|
| Create | `src/jobpilot/steps/bullet_scorer.py` | LLM tool schemas, `score_bullets()`, `rewrite_bullet()`, `_has_weak_verb()`, `question_for_rating()` |
| Create | `tests/test_bullet_scorer.py` | Unit tests for pure functions (no LLM) |
| Modify | `src/jobpilot/routes/profile.py` | `import html` hoisted, `_render_bullet_analysis()`, three new endpoints, clear scores in profile_save |
| Modify | `src/jobpilot/routes/wizard.py` | Fire-and-forget scoring after `commit_draft()` with proper task tracking |
| Modify | `src/jobpilot/resources/templates/html/profile_edit.html` | Analyze button, analysis panel, server-render existing scores |

---

## Task 1: `bullet_scorer.py` — pure functions + LLM tools

**Files:**
- Create: `src/jobpilot/steps/bullet_scorer.py`
- Create: `tests/test_bullet_scorer.py`

- [ ] **Step 1.1: Write failing tests for pure functions**

```python
# tests/test_bullet_scorer.py
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from jobpilot.steps.bullet_scorer import (
    _bullet_key,
    _has_weak_verb,
    question_for_rating,
)


def test_bullet_key_basic():
    assert _bullet_key(0, 0, 0) == "0-0-0"
    assert _bullet_key(2, 1, 3) == "2-1-3"


def test_weak_verb_passive():
    assert _has_weak_verb("was responsible for building the API") is True
    assert _has_weak_verb("helped the team ship faster") is True
    assert _has_weak_verb("assisted with onboarding 12 engineers") is True


def test_weak_verb_strong():
    assert _has_weak_verb("Led a team of 10 engineers") is False
    assert _has_weak_verb("Reduced P1 incidents 60% through RCA") is False
    assert _has_weak_verb("Built payments platform generating $26M") is False


def test_question_for_known_ratings():
    for rating in ["weak_no_metric", "weak_no_outcome", "weak_passive_verb", "vague"]:
        q = question_for_rating(rating)
        assert isinstance(q, str) and len(q) > 0


def test_question_for_unknown_rating_returns_fallback():
    q = question_for_rating("unknown_rating")
    assert isinstance(q, str) and len(q) > 0


def test_score_bullets_empty_profile_returns_empty_dict():
    # score_bullets with no experience should return {} without any LLM call
    from jobpilot.steps.bullet_scorer import score_bullets

    # Pass None for client/config/db — if LLM is called this will raise immediately
    assert score_bullets({"experience": []}, None, None, None) == {}


def test_score_bullets_no_experience_key():
    from jobpilot.steps.bullet_scorer import score_bullets

    assert score_bullets({}, None, None, None) == {}
```

- [ ] **Step 1.2: Run to confirm failures**

```
cd /Users/drewmerc/workspace/jobPilot && python -m pytest tests/test_bullet_scorer.py -v
```

Expected: `ModuleNotFoundError: No module named 'jobpilot.steps.bullet_scorer'`

- [ ] **Step 1.3: Implement `bullet_scorer.py`**

```python
# src/jobpilot/steps/bullet_scorer.py
import re

import anthropic

import jobpilot.llm as llm
from jobpilot.config import Config
from jobpilot.db import Database

WEAK_VERBS = frozenset([
    "helped",
    "worked on",
    "assisted with",
    "was responsible for",
    "participated in",
    "involved in",
    "contributed to",
    "supported",
    "collaborated on",
    "was involved",
])

_WEAK_VERB_RE = re.compile(
    r"^(" + "|".join(re.escape(v) for v in sorted(WEAK_VERBS, key=len, reverse=True)) + r")\b",
    re.IGNORECASE,
)

SCORE_BULLETS_TOOL = {
    "name": "score_bullets",
    "description": "Rate the quality of resume achievement bullets",
    "input_schema": {
        "type": "object",
        "properties": {
            "scores": {
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": {
                        "key": {
                            "type": "string",
                            "description": "Bullet identifier, format: exp_idx-pos_idx-bullet_idx",
                        },
                        "rating": {
                            "type": "string",
                            "enum": [
                                "strong",
                                "weak_no_metric",
                                "weak_no_outcome",
                                "weak_passive_verb",
                                "vague",
                            ],
                        },
                        "note": {"type": "string"},
                    },
                    "required": ["key", "rating"],
                },
            }
        },
        "required": ["scores"],
    },
}

_REWRITE_BULLET_TOOL = {
    "name": "rewrite_bullet",
    "description": "Rewrite a resume bullet using XYZ format",
    "input_schema": {
        "type": "object",
        "properties": {
            "rewritten": {
                "type": "string",
                "description": (
                    "Improved bullet. Starts with strong action verb. "
                    "XYZ format: Accomplished X, measured by Y, by doing Z. Single line."
                ),
            }
        },
        "required": ["rewritten"],
    },
}

_QUESTIONS = {
    "weak_no_metric": "What number captures the scale or result? (team size, % improvement, $ impact, time saved…)",
    "weak_no_outcome": "What was the end result or business impact of this work?",
    "weak_passive_verb": "What specifically did YOU do? Describe your direct contribution, starting with an action verb.",
    "vague": "Add a concrete example, outcome, or metric that shows real impact.",
}

_FALLBACK_QUESTION = "How can you make this more specific and impactful? (add a metric, outcome, or concrete example)"


def _bullet_key(exp_idx: int, pos_idx: int, bullet_idx: int) -> str:
    return f"{exp_idx}-{pos_idx}-{bullet_idx}"


def _has_weak_verb(text: str) -> bool:
    return bool(_WEAK_VERB_RE.match(text.strip()))


def question_for_rating(rating: str) -> str:
    return _QUESTIONS.get(rating, _FALLBACK_QUESTION)


def score_bullets(
    profile: dict,
    client: anthropic.Anthropic,
    config: Config,
    db: Database,
) -> dict:
    """Score all achievement bullets. Returns {} with no LLM call if no bullets."""
    bullets: list[dict] = []
    for exp_idx, exp in enumerate(profile.get("experience") or []):
        for pos_idx, pos in enumerate(exp.get("positions") or []):
            for bullet_idx, bullet in enumerate(pos.get("achievements") or []):
                if bullet.strip():
                    bullets.append(
                        {
                            "key": _bullet_key(exp_idx, pos_idx, bullet_idx),
                            "text": bullet.strip(),
                        }
                    )

    if not bullets:
        return {}

    prompt = (
        "Rate each resume achievement bullet for quality. Ratings:\n"
        "- strong: action verb + metric/outcome present, clear impact\n"
        "- weak_no_metric: no quantifiable data (numbers, %, $, scope)\n"
        "- weak_no_outcome: action described but no result stated\n"
        "- weak_passive_verb: passive language ('was responsible for', 'helped', etc.)\n"
        "- vague: too generic to differentiate this candidate\n\n"
        "Bullets to rate:\n"
        + "\n".join(f"[{b['key']}] {b['text']}" for b in bullets)
    )

    response = llm.call(
        client,
        db,
        "profile_score_bullets",
        model=config.llm_extract_model,
        max_tokens=2048,
        tools=[SCORE_BULLETS_TOOL],
        tool_choice={"type": "tool", "name": "score_bullets"},
        messages=[{"role": "user", "content": prompt}],
    )

    for block in response.content:
        if hasattr(block, "type") and block.type == "tool_use":
            return {
                s["key"]: {"rating": s["rating"], "note": s.get("note", "")}
                for s in block.input.get("scores", [])
            }

    return {}


def rewrite_bullet(
    bullet_text: str,
    rating: str,
    answer: str,
    client: anthropic.Anthropic,
    config: Config,
    db: Database,
) -> str:
    """Rewrite a single bullet given user's answer to the targeted follow-up question."""
    question = question_for_rating(rating)
    prompt = (
        f"Original bullet: {bullet_text}\n"
        f"Issue: {rating.replace('_', ' ')}\n"
        f"Question: {question}\n"
        f"User's answer: {answer}\n\n"
        "Rewrite using XYZ format: 'Accomplished X, measured by Y, by doing Z.' "
        "Start with a strong action verb. Single line. Preserve specifics from the original."
    )
    response = llm.call(
        client,
        db,
        "profile_rewrite_bullet",
        model=config.llm_tailor_model,
        max_tokens=256,
        tools=[_REWRITE_BULLET_TOOL],
        tool_choice={"type": "tool", "name": "rewrite_bullet"},
        messages=[{"role": "user", "content": prompt}],
    )
    for block in response.content:
        if hasattr(block, "type") and block.type == "tool_use":
            return block.input.get("rewritten", "")
    return ""
```

- [ ] **Step 1.4: Run tests — expect pass**

```
cd /Users/drewmerc/workspace/jobPilot && python -m pytest tests/test_bullet_scorer.py -v
```

Expected: all 8 tests PASS

- [ ] **Step 1.5: Commit**

```
git add src/jobpilot/steps/bullet_scorer.py tests/test_bullet_scorer.py
```

Write to `/tmp/msg.txt`:
```
feat(profile): add bullet_scorer step — LLM scoring + XYZ rewrite
```
Then: `git commit -F /tmp/msg.txt`

---

## Task 2: Score-bullets endpoint + render helper + profile_save fix

**Files:**
- Modify: `src/jobpilot/routes/profile.py`

### Key escaping rule for all HTML generation in this task

All Python values embedded in HTML attributes must go through `_html.escape(value, quote=True)`.
All Python values embedded in HTML attributes that hold JSON (e.g. `hx-vals`) must be built as a Python dict → `json.dumps(dict)` → `_html.escape(result, quote=True)`, then placed inside double-quoted HTML attribute: `hx-vals="..."`.

This handles both apostrophes in text values and double-quotes from json.dumps.

- [ ] **Step 2.1: Write failing test for render helper**

Add to `tests/test_bullet_scorer.py`:

```python
def test_render_bullet_analysis_all_strong():
    from jobpilot.routes.profile import _render_bullet_analysis

    profile = {
        "experience": [
            {
                "company": "Acme",
                "positions": [
                    {"title": "SWE", "dates": "2023-present", "achievements": ["Led team of 8"]}
                ],
            }
        ]
    }
    scores = {"0-0-0": {"rating": "strong", "note": ""}}
    html = _render_bullet_analysis(profile, scores)
    assert "strong" in html.lower() or "✓" in html


def test_render_bullet_analysis_shows_weak_bullets():
    from jobpilot.routes.profile import _render_bullet_analysis

    profile = {
        "experience": [
            {
                "company": "Acme",
                "positions": [
                    {
                        "title": "SWE",
                        "dates": "2023-present",
                        "achievements": ["Helped the team ship features"],
                    }
                ],
            }
        ]
    }
    scores = {"0-0-0": {"rating": "weak_passive_verb", "note": "Avoid 'helped'"}}
    html = _render_bullet_analysis(profile, scores)
    assert "Improve" in html
    # Apostrophe in bullet text must not break the hx-vals attribute
    assert "'" not in html.split('hx-vals="')[1].split('"')[0]
```

Run: `python -m pytest tests/test_bullet_scorer.py::test_render_bullet_analysis_all_strong -v`
Expected: `ImportError` (function doesn't exist yet)

- [ ] **Step 2.2: Hoist `import html` to top of `routes/profile.py`**

The existing file has `import html as _html` inside the `suggest_summary` function body (line 304). Move it to module level, removing the local import.

At the top of `routes/profile.py`, add with the other stdlib imports:
```python
import html as _html
```

Remove the local `import html as _html` inside `suggest_summary`.

- [ ] **Step 2.3: Add `_RATING_LABELS` constant and `_render_bullet_analysis` helper**

Add after existing helpers, before the routes section:

```python
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
            json.dumps({
                "exp_idx": str(ei),
                "pos_idx": str(pi),
                "bullet_idx": str(bi),
                "bullet_text": info["text"],
                "rating": rating,
                "ta_name": ta_name,
            }),
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
```

- [ ] **Step 2.4: Add `score_bullets_route` endpoint after `suggest_summary`**

```python
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
```

- [ ] **Step 2.5: Clear stale scores in `profile_save`**

In the existing `profile_save` route, after `profile["experience"] = experience` is assigned, add:

```python
    profile["experience"] = experience
    profile.pop("bullet_scores", None)  # scores are positional; stale after any experience edit
```

- [ ] **Step 2.6: Pass `bullet_analysis_html` from `profile_get`**

Replace the existing `profile_get` handler with:

```python
@router.get("/profile", response_class=HTMLResponse)
async def profile_get(request: Request) -> HTMLResponse:
    profile = request.app.state.profile_store.load() or {}
    bullet_analysis_html = ""
    if profile.get("bullet_scores") is not None:
        bullet_analysis_html = _render_bullet_analysis(profile, profile["bullet_scores"])
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
```

- [ ] **Step 2.7: Run tests**

```
cd /Users/drewmerc/workspace/jobPilot && python -m pytest tests/ -v
```

Expected: all tests PASS

- [ ] **Step 2.8: Commit**

Write to `/tmp/msg.txt`:
```
feat(profile): score-bullets endpoint, render helper, clear stale scores on save
```
`git add src/jobpilot/routes/profile.py tests/test_bullet_scorer.py && git commit -F /tmp/msg.txt`

---

## Task 3: Improve-bullet + Rewrite-bullet endpoints

**Files:**
- Modify: `src/jobpilot/routes/profile.py`

- [ ] **Step 3.1: Write failing tests**

Add to `tests/test_bullet_scorer.py`. These test the new HTTP endpoints via direct import of the pure data functions (not via test client). They fail now because the endpoints don't exist yet:

```python
def test_improve_bullet_endpoint_exists():
    # Verify the route will be importable once written
    import importlib
    import jobpilot.routes.profile as profile_mod
    assert hasattr(profile_mod, "improve_bullet"), "improve_bullet endpoint not yet defined"


def test_rewrite_bullet_endpoint_exists():
    import jobpilot.routes.profile as profile_mod
    assert hasattr(profile_mod, "rewrite_bullet_route"), "rewrite_bullet_route not yet defined"
```

Run: `python -m pytest tests/test_bullet_scorer.py::test_improve_bullet_endpoint_exists -v`
Expected: FAIL with `AssertionError: improve_bullet endpoint not yet defined`

- [ ] **Step 3.2: Add `improve_bullet` endpoint to `routes/profile.py`**

The improve-bullet response embeds all values in properly escaped HTML attributes.
Note the textarea **must** have both `id` and `name` — `hx-include` selects by CSS (id) but serializes by name.

```python
@router.post("/profile/improve-bullet", response_class=HTMLResponse)
async def improve_bullet(request: Request) -> HTMLResponse:
    from jobpilot.steps.bullet_scorer import question_for_rating

    form = await request.form()
    exp_idx = (form.get("exp_idx") or "0").strip()
    pos_idx = (form.get("pos_idx") or "0").strip()
    bullet_idx = (form.get("bullet_idx") or "0").strip()
    bullet_text = (form.get("bullet_text") or "").strip()
    rating = (form.get("rating") or "vague").strip()
    ta_name = (form.get("ta_name") or "").strip()

    if not bullet_text:
        return HTMLResponse(
            "<p class='muted' style='font-size:13px'>Bullet text missing.</p>"
        )

    question = question_for_rating(rating)
    answer_field = f"improve-answer-{exp_idx}-{pos_idx}-{bullet_idx}"
    rewrite_target = f"rewrite-result-{exp_idx}-{pos_idx}-{bullet_idx}"

    hx_vals = _html.escape(
        json.dumps({
            "exp_idx": exp_idx,
            "pos_idx": pos_idx,
            "bullet_idx": bullet_idx,
            "bullet_text": bullet_text,
            "rating": rating,
            "ta_name": ta_name,
        }),
        quote=True,
    )

    return HTMLResponse(f"""
<div style="margin-top:10px;padding:12px;background:var(--surface);border:1px solid var(--border);border-radius:var(--radius)">
  <label style="font-size:13px;font-weight:600">{_html.escape(question)}</label>
  <textarea id="{_html.escape(answer_field)}"
            name="{_html.escape(answer_field)}"
            rows="3"
            style="font-size:13px;resize:vertical;margin:6px 0 8px;display:block;width:100%"></textarea>
  <div style="display:flex;align-items:center;gap:8px">
    <button type="button" class="btn btn-outline btn-sm"
            hx-post="/profile/rewrite-bullet"
            hx-target="#{_html.escape(rewrite_target)}"
            hx-swap="innerHTML"
            hx-include="#{_html.escape(answer_field)}"
            hx-vals="{hx_vals}"
            onclick="this.disabled=true;this.querySelector('.btn-label').textContent='Rewriting…'"
            hx-on::after-request="this.disabled=false;this.querySelector('.btn-label').textContent='Rewrite bullet'">
      <span class="btn-label">Rewrite bullet</span>
    </button>
    <span class="muted" style="font-size:11px">~$0.01 in AI usage</span>
  </div>
  <div id="{_html.escape(rewrite_target)}"></div>
</div>
""")
```

- [ ] **Step 3.3: Add `rewrite_bullet_route` endpoint**

The "Use this" button uses data attributes + an extracted JS function to avoid embedding JSON in `onclick`.
Add a `<script>` block with `_applyBullet` to `base.html` (or inline once at the bottom of this response).

```python
@router.post("/profile/rewrite-bullet", response_class=HTMLResponse)
async def rewrite_bullet_route(request: Request) -> HTMLResponse:
    from jobpilot.steps.bullet_scorer import rewrite_bullet

    form = await request.form()
    exp_idx = (form.get("exp_idx") or "0").strip()
    pos_idx = (form.get("pos_idx") or "0").strip()
    bullet_idx_str = (form.get("bullet_idx") or "0").strip()
    bullet_text = (form.get("bullet_text") or "").strip()
    rating = (form.get("rating") or "vague").strip()
    ta_name = (form.get("ta_name") or "").strip()
    answer_field = f"improve-answer-{exp_idx}-{pos_idx}-{bullet_idx_str}"
    answer = (form.get(answer_field) or "").strip()

    if not bullet_text or not answer:
        return HTMLResponse(
            "<p class='muted' style='font-size:13px'>Please fill in the answer above.</p>"
        )

    try:
        improved = await asyncio.to_thread(
            rewrite_bullet,
            bullet_text,
            rating,
            answer,
            request.app.state.client,
            request.app.state.config,
            request.app.state.db,
        )
    except Exception as exc:
        logger.warning(f"Bullet rewrite failed: {exc}")
        return HTMLResponse(
            "<p class='muted' style='font-size:13px'>Rewrite failed — please try again.</p>"
        )

    if not improved:
        return HTMLResponse(
            "<p class='muted' style='font-size:13px'>No suggestion — add more detail above.</p>"
        )

    bullet_idx_int = int(bullet_idx_str) if bullet_idx_str.isdigit() else 0
    dismiss_id = f"rewrite-result-{exp_idx}-{pos_idx}-{bullet_idx_str}"

    # Use data attributes for LLM-generated text; JS reads them at click time.
    # This avoids any encoding issues with json.dumps values inside onclick="".
    return HTMLResponse(f"""
<div style="background:#f0f7ff;border:1px solid #b8d4f0;border-radius:6px;padding:12px;margin-top:8px">
  <p style="margin:0 0 4px;font-size:11px;font-weight:700;text-transform:uppercase;letter-spacing:.5px;color:var(--muted)">Suggested rewrite</p>
  <p style="margin:0 0 10px;font-size:13px;line-height:1.6">{_html.escape(improved)}</p>
  <button type="button" class="btn btn-primary btn-sm"
          data-ta="{_html.escape(ta_name, quote=True)}"
          data-line="{bullet_idx_int}"
          data-dismiss="{_html.escape(dismiss_id, quote=True)}"
          data-text="{_html.escape(improved, quote=True)}"
          onclick="(function(b){{
            var ta=document.querySelector('[name=&quot;'+b.dataset.ta+'&quot;]');
            if(ta){{
              var lines=ta.value.split('\\n');
              var idx=parseInt(b.dataset.line,10);
              if(idx<lines.length){{lines[idx]=b.dataset.text;}}
              else{{lines.push(b.dataset.text);}}
              ta.value=lines.join('\\n');
            }}
            var el=document.getElementById(b.dataset.dismiss);
            if(el)el.innerHTML='<span style=\\'color:var(--green);font-size:12px\\'>&#10003; Applied</span>';
          }})(this)">
    Use this
  </button>
  <button type="button" class="btn btn-outline btn-sm" style="margin-left:6px"
          data-dismiss="{_html.escape(dismiss_id, quote=True)}"
          onclick="var el=document.getElementById(this.dataset.dismiss);if(el)el.innerHTML=''">
    Discard
  </button>
</div>
""")
```

**Why data attributes:** LLM-generated text routinely contains `"`, `'`, `<`, `>`, and `\n`. Placing it in `data-text="{_html.escape(improved, quote=True)}"` lets the browser parse it safely; JS reads `button.dataset.text` at click time without any escaping concerns.

- [ ] **Step 3.4: Run all tests**

```
cd /Users/drewmerc/workspace/jobPilot && python -m pytest tests/ -v
```

Expected: all tests PASS

- [ ] **Step 3.5: Commit**

Write to `/tmp/msg.txt`:
```
feat(profile): improve-bullet + rewrite-bullet HTMX endpoints (data-attr pattern)
```
`git add src/jobpilot/routes/profile.py && git commit -F /tmp/msg.txt`

---

## Task 4: UI — Analyze button + analysis panel

**Files:**
- Modify: `src/jobpilot/resources/templates/html/profile_edit.html`

- [ ] **Step 4.1: Replace Experience section header**

Find: `<h3 style="margin:0 0 16px;font-size:15px">Experience</h3>`

Replace with:

```html
<div style="display:flex;align-items:center;justify-content:space-between;margin-bottom:16px">
  <h3 style="margin:0;font-size:15px">Experience</h3>
  <div style="display:flex;align-items:center;gap:10px">
    <button type="button" class="btn btn-outline btn-sm"
            hx-post="/profile/score-bullets"
            hx-target="#bullet-analysis-panel"
            hx-swap="innerHTML"
            onclick="this.disabled=true;this.querySelector('.btn-label').textContent='Analyzing…';this.querySelector('.spin-icon').style.display='inline-block'"
            hx-on::after-request="this.disabled=false;this.querySelector('.btn-label').textContent='✦ Analyze bullets';this.querySelector('.spin-icon').style.display='none'"
            data-tooltip="Scores every achievement bullet for quality — flags weak verbs, missing metrics, vague outcomes. ~$0.02.">
      <span class="spin-icon" style="display:none;width:12px;height:12px;border:2px solid #aaa;border-top-color:#555;border-radius:50%;animation:spin .7s linear infinite;vertical-align:middle;margin-right:5px"></span><span class="btn-label">✦ Analyze bullets</span>
    </button>
    <span class="muted" style="font-size:11px">~$0.02 · 10–15 s</span>
  </div>
</div>
```

- [ ] **Step 4.2: Add analysis panel div after the Experience card's closing `</div>`**

The Experience card ends with `{% endfor %}` followed by `</div>`. After that closing div, insert:

```html
<div id="bullet-analysis-panel" style="margin-bottom:16px">
  {% if bullet_analysis_html is defined and bullet_analysis_html %}
  {{ bullet_analysis_html | safe }}
  {% endif %}
</div>
```

- [ ] **Step 4.3: Run tests**

```
cd /Users/drewmerc/workspace/jobPilot && python -m pytest tests/ -v
```

Expected: all PASS

- [ ] **Step 4.4: Start app and manually verify**

```
cd /Users/drewmerc/workspace/jobPilot && python -m uvicorn jobpilot.app:create_app --factory --port 8000 --reload
```

Check:
1. `http://localhost:8000/profile` — "✦ Analyze bullets" button visible in Experience header
2. Click Analyze — analysis panel populates with rated bullets
3. On a weak bullet, click "✦ Improve" — targeted question form appears inline
4. Fill in an answer, click "Rewrite bullet" — suggestion card appears
5. Click "Use this" — correct line in textarea updates; verify by counting newlines to confirm correct line index
6. Refresh page — scores panel server-renders from stored `bullet_scores`
7. Save profile (submit form) — verify `bullet_scores` is gone from profile.json (scores cleared on save)

- [ ] **Step 4.5: Commit**

Write to `/tmp/msg.txt`:
```
feat(profile): bullet analysis panel — analyze button, HTMX panel, server-render scores
```
`git add src/jobpilot/resources/templates/html/profile_edit.html && git commit -F /tmp/msg.txt`

---

## Task 5: Auto-trigger scoring after wizard upload

**Files:**
- Modify: `src/jobpilot/routes/wizard.py`

- [ ] **Step 5.1: Add background scoring in `step2_post` with task reference tracking**

In `wizard.py`, after `profile_store.commit_draft()` on the line following `profile_store.save_draft(profile)`:

```python
    profile_store.save_draft(profile)
    profile_store.commit_draft()

    # Fire-and-forget bullet scoring so the profile tab shows quality badges
    # immediately after the first upload without any manual trigger.
    # Keep a strong reference to the task to prevent GC before completion.
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
                committed_profile["bullet_scores"] = scores
                app_state.profile_store.save(committed_profile)
        except Exception as exc:
            logger.warning(f"Background bullet scoring failed: {exc}")

    _bg_task = asyncio.create_task(_bg_score(request.app.state, profile))
    _bg_task.add_done_callback(lambda _: None)  # prevents "task was destroyed but pending" warning

    return RedirectResponse("/wizard/step/3", status_code=303)
```

Note: `_bg_task` is a local variable in `step2_post`. Its reference is held until `add_done_callback` fires, preventing CPython from garbage-collecting the task mid-execution. The lambda callback is a no-op; it just keeps the reference alive until completion.

- [ ] **Step 5.2: Run tests**

```
cd /Users/drewmerc/workspace/jobPilot && python -m pytest tests/ -v
```

Expected: all PASS

- [ ] **Step 5.3: Commit**

Write to `/tmp/msg.txt`:
```
feat(wizard): auto-score bullets after resume upload (background task)
```
`git add src/jobpilot/routes/wizard.py && git commit -F /tmp/msg.txt`

---

## Acceptance Criteria

- [ ] `python -m pytest tests/ -v` — all tests pass
- [ ] `/profile` shows "✦ Analyze bullets" button in Experience header
- [ ] Clicking Analyze populates analysis panel with per-bullet ratings
- [ ] Weak bullets show rating badge (No metric / No outcome / Passive verb / Vague)
- [ ] "✦ Improve" button on weak bullet shows targeted follow-up question inline
- [ ] Submitting an answer produces a rewrite suggestion card
- [ ] "Use this" replaces the correct line in the correct textarea (verified by line index)
- [ ] Apostrophes and quotes in bullet text do not break any HTML attribute or JS
- [ ] Refreshing `/profile` after scoring shows panel pre-populated (server-render)
- [ ] Saving the profile form clears `bullet_scores` from `profile.json`
- [ ] After wizard step 2 completes, `profile.json` gains `bullet_scores` key within seconds
- [ ] Empty experience → score-bullets returns empty panel, no LLM call, no error
