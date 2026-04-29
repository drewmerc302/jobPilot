"""Company discovery: given anchor companies + keywords, suggest similar companies."""

import logging

import anthropic

import jobpilot.llm as llm
from jobpilot.config import Config
from jobpilot.db import Database

logger = logging.getLogger(__name__)

DISCOVER_TOOL = {
    "name": "discover_companies",
    "description": "Suggest companies similar to the anchor list for a job search",
    "input_schema": {
        "type": "object",
        "properties": {
            "companies": {
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": {
                        "name": {"type": "string"},
                        "reason": {
                            "type": "string",
                            "description": "One sentence: why this company fits the search",
                        },
                    },
                    "required": ["name", "reason"],
                },
            }
        },
        "required": ["companies"],
    },
}


def discover_companies(
    anchor_companies: list[str],
    keywords: list[str],
    client: anthropic.Anthropic,
    config: Config,
    db: Database,
) -> list[dict]:
    """Return up to 15 company suggestions similar to the anchor list.

    Each item: {"name": str, "reason": str}.
    Returns [] on failure.
    """
    anchors_str = ", ".join(anchor_companies) if anchor_companies else "none specified"
    keywords_str = ", ".join(keywords) if keywords else "general"

    prompt = (
        f"The candidate is searching for roles in: {keywords_str}\n"
        f"Companies they already like: {anchors_str}\n\n"
        "Suggest 10-15 similar companies they should also consider. "
        "Focus on companies with similar culture, scale, or domain. "
        "Each suggestion needs a one-sentence reason why it fits."
    )

    try:
        response = llm.call(
            client,
            db,
            "discover_companies",
            model=config.llm_filter_model,
            max_tokens=1024,
            tools=[DISCOVER_TOOL],
            tool_choice={"type": "tool", "name": "discover_companies"},
            messages=[{"role": "user", "content": prompt}],
        )
        for block in response.content:
            if hasattr(block, "type") and block.type == "tool_use":
                return block.input.get("companies", [])
    except Exception as e:
        logger.error(f"Company discovery failed: {e}")

    return []
