import json
import os
from dataclasses import dataclass, field
from pathlib import Path

from dotenv import load_dotenv

# User data lives outside the bundle so it survives app updates.
# Dev override: set JOBPILOT_DATA_DIR in your shell or a .env file.
_USER_DATA_DIR = Path(os.getenv("JOBPILOT_DATA_DIR", Path.home() / ".jobpilot"))

# Load .env from the user data dir (lets advanced users drop a key file there)
# then fall back to CWD-based search (useful in dev with a project-root .env).
load_dotenv(_USER_DATA_DIR / ".env")
load_dotenv()


@dataclass
class Config:
    anthropic_api_key: str = field(
        default_factory=lambda: os.getenv("ANTHROPIC_API_KEY", "")
    )
    llm_filter_model: str = "claude-haiku-4-5-20251001"
    llm_tailor_model: str = "claude-sonnet-4-6"
    llm_extract_model: str = "claude-haiku-4-5-20251001"
    relevance_threshold: float = 0.6
    data_dir: Path = field(default_factory=lambda: _USER_DATA_DIR)
    db_path: Path = field(default_factory=lambda: _USER_DATA_DIR / "jobpilot.db")
    output_dir: Path = field(default_factory=lambda: _USER_DATA_DIR / "output")
    template_dir: Path = field(
        default_factory=lambda: Path(__file__).parent / "resources" / "templates"
    )
    adzuna_app_id: str = field(default_factory=lambda: os.getenv("ADZUNA_APP_ID", ""))
    adzuna_app_key: str = field(default_factory=lambda: os.getenv("ADZUNA_APP_KEY", ""))
    jooble_api_key: str = field(default_factory=lambda: os.getenv("JOOBLE_API_KEY", ""))
    monthly_budget: float = 5.00
    total_budget: float = 10.00
    has_byo_key: bool = False
    max_runs_per_day: int = field(
        default_factory=lambda: int(os.getenv("JOBPILOT_MAX_RUNS_PER_DAY", "4"))
    )

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
