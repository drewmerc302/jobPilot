import copy
import json
import logging
import platform
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


def _typst_binary(config: Config) -> Path:
    system = platform.system().lower()
    if system == "darwin":
        return config.template_dir.parent / "typst" / "macos" / "typst"
    if system == "windows":
        return config.template_dir.parent / "typst" / "windows" / "typst.exe"
    return config.template_dir.parent / "typst" / "linux" / "typst"


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
    result = copy.deepcopy(resume_data)
    edits_to_apply = {
        edit["original"]: edit["suggested"]
        for i, edit in enumerate(edits, 1)
        if i in adopt_indices
    }
    if not edits_to_apply:
        return result

    if "summary" in result:
        for original, suggested in edits_to_apply.items():
            if original in result["summary"]:
                result["summary"] = result["summary"].replace(original, suggested)

    for exp in result.get("experience", []):
        for field in ("bullets", "achievements"):
            items = exp.get(field, [])
            for j, item in enumerate(items):
                for original, suggested in edits_to_apply.items():
                    if original in item:
                        items[j] = item.replace(original, suggested)
        for pos in exp.get("positions", []):
            for field in ("achievements", "bullets"):
                items = pos.get(field, [])
                for j, item in enumerate(items):
                    for original, suggested in edits_to_apply.items():
                        if original in item:
                            items[j] = item.replace(original, suggested)

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
        client = anthropic.Anthropic(api_key=config.anthropic_api_key)
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
                "/",
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
    job_dir = output_dir / f"{job['company']}_{job['id'].replace(':', '_')}"
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
