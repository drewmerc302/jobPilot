import re

import anthropic

import jobpilot.llm as llm
from jobpilot.config import Config
from jobpilot.db import Database

WEAK_VERBS = frozenset(
    [
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
    ]
)

_WEAK_VERB_RE = re.compile(
    r"^("
    + "|".join(re.escape(v) for v in sorted(WEAK_VERBS, key=len, reverse=True))
    + r")\b",
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
        "Bullets to rate:\n" + "\n".join(f"[{b['key']}] {b['text']}" for b in bullets)
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
