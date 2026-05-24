import logging
import shutil
import subprocess
import urllib.parse
import urllib.request
from pathlib import Path

import anthropic
import yaml
from tenacity import (
    retry,
    retry_if_exception_type,
    stop_after_attempt,
    wait_exponential,
)

from jobpilot import llm as llm_module
from jobpilot.config import Config
from jobpilot.db import Database
from jobpilot.steps.tailor import PdfGenerationError, _typst_binary

logger = logging.getLogger(__name__)

_llm_retry = retry(
    stop=stop_after_attempt(3),
    wait=wait_exponential(multiplier=1, min=2, max=10),
    retry=retry_if_exception_type((anthropic.APIError, anthropic.APIConnectionError)),
    reraise=True,
)

PREP_TOOL = {
    "name": "interview_prep",
    "description": "Generate structured interview preparation content for a job",
    "input_schema": {
        "type": "object",
        "properties": {
            "likely_questions": {
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": {
                        "question": {"type": "string"},
                        "suggested_answer": {
                            "type": "string",
                            "description": "A strong suggested answer drawing on the candidate's resume and experience",
                        },
                        "rationale": {
                            "type": "string",
                            "description": "Why this question is likely and why this answer works",
                        },
                    },
                    "required": ["question", "suggested_answer", "rationale"],
                },
                "description": "Predicted behavioral and technical interview questions with suggested answers",
            },
            "star_stories": {
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": {
                        "question": {"type": "string"},
                        "resume_bullet": {"type": "string"},
                        "situation": {"type": "string"},
                        "task": {"type": "string"},
                        "action": {"type": "string"},
                        "result": {"type": "string"},
                    },
                    "required": [
                        "question",
                        "resume_bullet",
                        "situation",
                        "task",
                        "action",
                        "result",
                    ],
                },
                "description": "STAR story mappings from resume experience to interview questions",
            },
            "talking_points": {
                "type": "array",
                "items": {"type": "string"},
                "description": "3-5 key things to emphasize about your background for this specific role",
            },
            "red_flags": {
                "type": "array",
                "items": {"type": "string"},
                "description": "Gaps or weaknesses relative to the JD to prepare for",
            },
        },
        "required": ["likely_questions", "star_stories", "talking_points", "red_flags"],
    },
}


def _most_recent_role(resume_data: dict) -> str:
    """Extract the candidate's most recent job title for use in the prompt."""
    experience = resume_data.get("experience", [])
    if experience:
        first = experience[0]
        title = first.get("title", "")
        if title:
            return title
        positions = first.get("positions", [])
        if positions:
            return positions[0].get("title", "professional")
    return "professional"


def _web_research(company: str) -> str:
    try:
        url = f"https://en.wikipedia.org/api/rest_v1/page/summary/{urllib.parse.quote(company)}"
        with urllib.request.urlopen(url, timeout=5) as r:
            import json

            data = json.loads(r.read())
            return data.get("extract", "")[:500]
    except Exception:
        return ""


@_llm_retry
def _call_llm(
    job: dict,
    resume_data: dict,
    config: Config,
    client: anthropic.Anthropic,
    db: Database,
    extra_context: str = "",
) -> dict:
    role = _most_recent_role(resume_data)
    llm_keys = {
        k: v
        for k, v in resume_data.items()
        if k not in ("bullet_scores", "low_confidence_fields")
    }
    resume_text = yaml.dump(llm_keys, default_flow_style=False)[:4000]

    prompt = f"""You are preparing a {role} candidate for an interview.

Job: {job["company"]} — {job["title"]}
Description:
{(job.get("description") or "")[:3000]}

Candidate's resume (YAML):
{resume_text}
"""
    if extra_context:
        prompt += f"\nAdditional company context:\n{extra_context}\n"

    prompt += (
        "\nGenerate structured interview prep content using the interview_prep tool."
    )

    response = llm_module.call(
        client,
        db,
        "interview_prep",
        job_id=job.get("id"),
        model=config.llm_tailor_model,
        max_tokens=2000,
        tools=[PREP_TOOL],
        tool_choice={"type": "any"},
        messages=[{"role": "user", "content": prompt}],
    )

    for block in response.content:
        if hasattr(block, "type") and block.type == "tool_use":
            return block.input

    raise ValueError("LLM did not return tool_use block")


def generate_interview_prep(
    db: Database,
    job_id: str,
    resume_data: dict,
    config: Config,
    client: anthropic.Anthropic,
    research: bool = False,
) -> dict | None:
    """Generate interview prep content for a job.

    Returns a dict of prep content (likely_questions, star_stories, talking_points,
    red_flags), or None on failure. The caller renders this as HTML.
    PDF export is deferred to v1.x.
    """
    job = db.get_job(job_id)
    if not job:
        logger.warning(f"interview_prep: job {job_id} not found")
        return None

    extra_context = ""
    if research:
        logger.info(f"interview_prep: fetching company research for {job['company']}")
        extra_context = _web_research(job["company"])

    try:
        return _call_llm(dict(job), resume_data, config, client, db, extra_context)
    except Exception as e:
        logger.error(f"interview_prep: LLM call failed for {job_id}: {e}")
        return None


def generate_interview_prep_pdf(
    prep_data: dict,
    job_title: str,
    company: str,
    output_dir: Path,
    config: Config,
) -> Path:
    """Compile interview-prep JSON -> PDF via bundled Typst binary.

    Raises PdfGenerationError with a user-readable reason on failure.
    """
    output_dir.mkdir(parents=True, exist_ok=True)
    yaml_path = output_dir / "interview_prep_data.yaml"
    src_template = config.template_dir / "interview_prep.typ"
    local_template = output_dir / "interview_prep.typ"
    pdf_path = output_dir / "interview_prep.pdf"

    data = {
        "job_title": job_title,
        "company": company,
        **{
            k: prep_data[k]
            for k in ("talking_points", "red_flags", "star_stories", "likely_questions")
            if k in prep_data
        },
    }

    with open(yaml_path, "w", encoding="utf-8") as f:
        yaml.dump(data, f, default_flow_style=False, allow_unicode=True)

    typst_bin = _typst_binary(config)
    if not typst_bin.exists():
        raise PdfGenerationError(f"Typst binary not found at {typst_bin}")
    if not src_template.exists():
        raise PdfGenerationError(f"Interview prep template not found at {src_template}")

    shutil.copyfile(src_template, local_template)

    try:
        subprocess.run(
            [
                str(typst_bin),
                "compile",
                "interview_prep.typ",
                "interview_prep.pdf",
                "--input",
                "data=interview_prep_data.yaml",
                "--root",
                str(output_dir),
            ],
            check=True,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            cwd=str(output_dir),
        )
        return pdf_path
    except subprocess.CalledProcessError as e:
        raise PdfGenerationError(f"Typst compile failed: {e.stderr}") from e
