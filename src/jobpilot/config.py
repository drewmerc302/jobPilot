import json
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
    llm_extract_model: str = "claude-haiku-4-5-20251001"
    relevance_threshold: float = 0.6
    data_dir: Path = field(default_factory=lambda: PROJECT_ROOT / "data")
    db_path: Path = field(default_factory=lambda: PROJECT_ROOT / "data" / "jobpilot.db")
    output_dir: Path = field(default_factory=lambda: PROJECT_ROOT / "output")
    template_dir: Path = field(
        default_factory=lambda: Path(__file__).parent / "resources" / "templates"
    )
    adzuna_app_id: str = field(default_factory=lambda: os.getenv("ADZUNA_APP_ID", ""))
    adzuna_app_key: str = field(default_factory=lambda: os.getenv("ADZUNA_APP_KEY", ""))
    monthly_budget: float = 5.00
    total_budget: float = 10.00
    has_byo_key: bool = False

    def __post_init__(self):
        overrides_path = self.data_dir / "config_overrides.json"
        if overrides_path.exists():
            try:
                overrides = json.loads(overrides_path.read_text())
                if "anthropic_api_key" in overrides:
                    self.anthropic_api_key = overrides["anthropic_api_key"]
                if "monthly_budget" in overrides:
                    self.monthly_budget = float(overrides["monthly_budget"])
                if "total_budget" in overrides:
                    self.total_budget = float(overrides["total_budget"])
                if "has_byo_key" in overrides:
                    self.has_byo_key = bool(overrides["has_byo_key"])
            except Exception:
                pass

    def save_overrides(self, **kwargs) -> None:
        """Persist mutable user overrides to data_dir/config_overrides.json."""
        overrides_path = self.data_dir / "config_overrides.json"
        existing: dict = {}
        if overrides_path.exists():
            try:
                existing = json.loads(overrides_path.read_text())
            except Exception:
                pass
        existing.update({k: v for k, v in kwargs.items() if v is not None})
        tmp = overrides_path.with_suffix(".tmp")
        tmp.write_text(json.dumps(existing, ensure_ascii=False, indent=2))
        tmp.replace(overrides_path)
