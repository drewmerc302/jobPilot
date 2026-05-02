import copy
import json
import logging
import platform
import re
import subprocess
from pathlib import Path

import anthropic
import yaml

import jobpilot.llm as llm
from jobpilot.config import Config
from jobpilot.db import Database
from jobpilot.llm import llm_retry

logger = logging.getLogger(__name__)

ANALYSIS_TOOL = {
    "name": "resume_analysis",
    "description": "Analyze resume against job description and suggest improvements",
    "input_schema": {
        "type": "object",
        "properties": {
            "reordered_bullets": {
                "type": "object",
                "description": "Map of 'Company - Title' to reordered bullet list",
                "additionalProperties": {"type": "array", "items": {"type": "string"}},
            },
            "suggested_edits": {
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": {
                        "original": {"type": "string"},
                        "suggested": {"type": "string"},
                        "reason": {"type": "string"},
                    },
                    "required": ["original", "suggested", "reason"],
                },
            },
            "keyword_gaps": {
                "type": "array",
                "items": {"type": "string"},
                "description": "Keywords in the JD missing from the resume",
            },
            "key_requirements": {
                "type": "array",
                "items": {"type": "string"},
                "description": "Top requirements from the job description",
            },
            "interview_talking_points": {
                "type": "array",
                "items": {"type": "string"},
                "description": "What the candidate should emphasize in interviews",
            },
        },
        "required": [
            "reordered_bullets",
            "suggested_edits",
            "keyword_gaps",
            "key_requirements",
            "interview_talking_points",
        ],
    },
}


_UNSAFE_PATH_CHARS = re.compile(r'[<>:"/\\|?*\x00-\x1f]')


def _safe_dirname(s: str, max_len: int = 80) -> str:
    """Strip filesystem-illegal chars (Windows + POSIX) and trim.

    Replaces any of `< > : " / \\ | ? *` plus control chars with `_`,
    collapses runs of `_`, strips leading/trailing whitespace and dots
    (Windows hates trailing dots), and truncates. Always returns at
    least `_` to avoid empty path segments.
    """
    cleaned = _UNSAFE_PATH_CHARS.sub("_", s or "")
    cleaned = re.sub(r"\s*_\s*", "_", cleaned)
    cleaned = re.sub(r"_+", "_", cleaned).strip(" ._")
    cleaned = cleaned[:max_len].rstrip(" ._")
    return cleaned or "_"


def _typst_binary(config: Config) -> Path:
    system = platform.system().lower()
    machine = platform.machine().lower()
    base = config.template_dir.parent / "typst"
    if system == "darwin":
        arch_dir = "macos-arm64" if machine in ("arm64", "aarch64") else "macos-x86_64"
        candidate = base / arch_dir / "typst"
        if candidate.exists():
            return candidate
        legacy = base / "macos" / "typst"
        if legacy.exists():
            return legacy
        return candidate
    if system == "windows":
        return base / "windows" / "typst.exe"
    return base / "linux" / "typst"


def reorder_resume_yaml(resume_data: dict, reorder_map: dict) -> dict:
    result = copy.deepcopy(resume_data)
    for exp in result.get("experience", []):
        for pos in exp.get("positions", []):
            key = f"{exp.get('company', '')} - {pos.get('title', '')}"
            if key in reorder_map:
                new_order = reorder_map[key]
                existing = pos.get("achievements", [])
                reordered = [b for b in new_order if b in existing]
                remaining = [b for b in existing if b not in reordered]
                pos["achievements"] = reordered + remaining
    return result


def apply_suggested_edits(
    resume_data: dict, edits: list[dict], adopt_indices: set[int]
) -> dict:
    """Apply LLM-suggested edits to a resume.

    Exact-match-first: if any list item equals `original` verbatim, only
    that item is rewritten. The substring fallback only fires when no
    exact match exists in any of the bullet pools — this prevents one
    bullet's text from being rewritten just because another bullet
    contains it as a substring (e.g. "led the team" inside "led the
    team that...").
    """
    result = copy.deepcopy(resume_data)
    edits_to_apply = {
        edit["original"]: edit["suggested"]
        for i, edit in enumerate(edits, 1)
        if i in adopt_indices
    }
    if not edits_to_apply:
        return result

    # Collect every bullet pool we may touch so we can detect whether an
    # exact match exists before resorting to substring replace.
    bullet_pools: list[list] = []
    for exp in result.get("experience", []):
        for field in ("bullets", "achievements"):
            if isinstance(exp.get(field), list):
                bullet_pools.append(exp[field])
        for pos in exp.get("positions", []):
            for field in ("achievements", "bullets"):
                if isinstance(pos.get(field), list):
                    bullet_pools.append(pos[field])

    summary_text = (
        result.get("summary", "") if isinstance(result.get("summary"), str) else ""
    )

    for original, suggested in edits_to_apply.items():
        exact_in_summary = summary_text == original
        exact_in_bullets = any(
            any(item == original for item in pool) for pool in bullet_pools
        )

        if exact_in_summary:
            result["summary"] = suggested
            continue

        if exact_in_bullets:
            for pool in bullet_pools:
                for j, item in enumerate(pool):
                    if item == original:
                        pool[j] = suggested
            continue

        # Substring fallback (last resort)
        logger.info(
            "apply_suggested_edits fallback: no exact match for "
            "%r, using substring replace",
            original[:80],
        )
        if isinstance(result.get("summary"), str) and original in result["summary"]:
            result["summary"] = result["summary"].replace(original, suggested)
        for pool in bullet_pools:
            for j, item in enumerate(pool):
                if isinstance(item, str) and original in item:
                    pool[j] = item.replace(original, suggested)

    return result


@llm_retry
def llm_resume_analysis(
    resume_yaml_str: str,
    job_description: str,
    config: Config,
    client: anthropic.Anthropic | None = None,
    db: Database | None = None,
    job_id: str | None = None,
) -> dict:
    if client is None:
        client = anthropic.Anthropic(api_key=config.anthropic_api_key, timeout=90)
    # B6.5: cap the JD text we send. 8k chars ≈ 2k tokens — keeps the bill
    # bounded if a paste-bomb description sneaks in.
    MAX_JD_CHARS = 8_000
    if isinstance(job_description, str) and len(job_description) > MAX_JD_CHARS:
        logger.info(
            "Truncating job_description from %d to %d chars before LLM call",
            len(job_description),
            MAX_JD_CHARS,
        )
        job_description = job_description[:MAX_JD_CHARS]
    kwargs = dict(
        model=config.llm_tailor_model,
        max_tokens=4096,
        tools=[ANALYSIS_TOOL],
        tool_choice={"type": "tool", "name": "resume_analysis"},
        messages=[
            {
                "role": "user",
                "content": f"""Analyze this resume against the job description. Reorder bullets to prioritize
relevance to the JD, suggest wording improvements for better keyword alignment,
identify keyword gaps, extract the top requirements from the job description,
and suggest what the candidate should emphasize in interviews.

RESUME (YAML):
{resume_yaml_str}

JOB DESCRIPTION:
{job_description}""",
            }
        ],
    )
    if db is not None:
        response = llm.call(client, db, "tailor", job_id=job_id, **kwargs)
    else:
        response = client.messages.create(**kwargs)
    for block in response.content:
        if block.type == "tool_use":
            return block.input
    return {
        "reordered_bullets": {},
        "suggested_edits": [],
        "keyword_gaps": [],
        "key_requirements": [],
        "interview_talking_points": [],
    }


def ensure_analysis(
    job: dict,
    resume_data: dict,
    db: Database,
    config: Config,
    force: bool = False,
    client: anthropic.Anthropic | None = None,
) -> dict:
    """Run Sonnet resume analysis on-demand, caching results in DB.

    resume_data is passed explicitly — storage location is a Phase 2 concern.
    Returns the full analysis dict including reordered_bullets.
    When served from cache, reordered_bullets is {}.
    """
    match = db.get_match(job["id"])
    existing = json.loads(match.get("suggestions") or "{}") if match else {}

    if existing.get("suggested_edits") and not force:
        existing.setdefault("reordered_bullets", {})
        return existing

    if not job.get("description"):
        existing.setdefault("reordered_bullets", {})
        return existing

    try:
        resume_yaml_str = yaml.dump(resume_data, default_flow_style=False)
        analysis = llm_resume_analysis(
            resume_yaml_str,
            job["description"],
            config,
            client=client,
            db=db,
            job_id=job.get("id"),
        )
    except Exception:
        logger.warning(f"LLM analysis failed for {job['id']}, using cached suggestions")
        existing.setdefault("reordered_bullets", {})
        return existing

    merged = {
        "suggested_edits": analysis.get("suggested_edits", []),
        "keyword_gaps": analysis.get("keyword_gaps", []),
        "key_requirements": analysis.get("key_requirements", [])
        or existing.get("key_requirements", []),
        "interview_talking_points": analysis.get("interview_talking_points", [])
        or existing.get("interview_talking_points", []),
    }
    db.update_match_suggestions(job["id"], json.dumps(merged))

    return {**merged, "reordered_bullets": analysis.get("reordered_bullets", {})}


def generate_resume_pdf(
    resume_data: dict, output_dir: Path, config: Config
) -> Path | None:
    """Compile resume YAML → PDF via bundled Typst binary.

    resume_data is passed explicitly — storage location is a Phase 2 concern.
    """
    output_dir.mkdir(parents=True, exist_ok=True)
    yaml_path = output_dir / "resume.yaml"
    template_path = config.template_dir / "resume.typ"
    pdf_path = output_dir / "resume.pdf"

    with open(yaml_path, "w") as f:
        yaml.dump(resume_data, f, default_flow_style=False, allow_unicode=True)

    typst_bin = _typst_binary(config)
    if not typst_bin.exists():
        logger.error(f"Typst binary not found at {typst_bin}")
        return None
    if not template_path.exists():
        logger.error(f"Resume template not found at {template_path}")
        return None

    try:
        subprocess.run(
            [
                str(typst_bin),
                "compile",
                str(template_path),
                str(pdf_path),
                "--input",
                f"resume={yaml_path}",
                "--root",
                str(template_path.parent),
            ],
            check=True,
            capture_output=True,
            text=True,
        )
        return pdf_path
    except subprocess.CalledProcessError as e:
        logger.error(f"Resume PDF generation failed: {e.stderr}")
        return None


def run_tailor_for_job(
    job: dict,
    analysis: dict,
    resume_data: dict,
    output_dir: Path,
    config: Config,
    adopt_edits: set[int] | None = None,
) -> dict:
    """Generate a tailored resume PDF for a job.

    resume_data is passed explicitly — storage location is a Phase 2 concern.
    """
    safe_company = _safe_dirname(job.get("company", ""))
    safe_job_id = _safe_dirname(job["id"].replace(":", "_"))
    job_dir = output_dir / f"{safe_company}_{safe_job_id}"
    tailored = reorder_resume_yaml(resume_data, analysis.get("reordered_bullets", {}))

    if adopt_edits:
        edits = analysis.get("suggested_edits", [])
        tailored = apply_suggested_edits(tailored, edits, adopt_edits)
        logger.info(f"Applied {len(adopt_edits)} suggested edits to resume")

    resume_pdf = generate_resume_pdf(tailored, job_dir, config)
    return {
        "job_id": job["id"],
        "resume_pdf": resume_pdf,
        "analysis": analysis,
    }
