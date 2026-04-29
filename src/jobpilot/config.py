import os
from dataclasses import dataclass, field
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()

PROJECT_ROOT = Path(__file__).parent.parent.parent


@dataclass
class Config:
    anthropic_api_key: str = field(
        default_factory=lambda: os.getenv("ANTHROPIC_API_KEY", "")
    )
    llm_filter_model: str = "claude-haiku-4-5-20251001"
    llm_tailor_model: str = "claude-sonnet-4-6"
    relevance_threshold: float = 0.6
    db_path: Path = field(default_factory=lambda: PROJECT_ROOT / "data" / "jobpilot.db")
    output_dir: Path = field(default_factory=lambda: PROJECT_ROOT / "output")
    template_dir: Path = field(
        default_factory=lambda: Path(__file__).parent / "resources" / "templates"
    )
