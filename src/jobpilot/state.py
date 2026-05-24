import dataclasses
import json
from pathlib import Path

from jobpilot.search_params import SearchParams


class ProfileStore:
    def __init__(self, data_dir: Path):
        self._dir = data_dir
        self._path = data_dir / "profile.json"
        self._draft = data_dir / "profile_draft.json"

    def load(self) -> dict | None:
        if not self._path.exists():
            return None
        return json.loads(self._path.read_text(encoding="utf-8"))

    def save(self, profile: dict) -> None:
        self._dir.mkdir(parents=True, exist_ok=True)
        tmp = self._path.with_suffix(".tmp")
        tmp.write_text(
            json.dumps(profile, ensure_ascii=False, indent=2), encoding="utf-8"
        )
        tmp.replace(self._path)

    def load_draft(self) -> dict | None:
        if not self._draft.exists():
            return None
        return json.loads(self._draft.read_text(encoding="utf-8"))

    def save_draft(self, profile: dict) -> None:
        self._dir.mkdir(parents=True, exist_ok=True)
        tmp = self._draft.with_suffix(".tmp")
        tmp.write_text(
            json.dumps(profile, ensure_ascii=False, indent=2), encoding="utf-8"
        )
        tmp.replace(self._draft)

    def commit_draft(self) -> None:
        """Promote draft to confirmed profile."""
        if self._draft.exists():
            self._draft.replace(self._path)

    def has_profile(self) -> bool:
        return self._path.exists()

    def has_draft(self) -> bool:
        return self._draft.exists()


class SearchParamsStore:
    def __init__(self, data_dir: Path):
        self._dir = data_dir
        self._path = data_dir / "search_params.json"

    def load(self) -> SearchParams | None:
        if not self._path.exists():
            return None
        d = json.loads(self._path.read_text(encoding="utf-8"))
        return SearchParams(**d)

    def save(self, params: SearchParams) -> None:
        self._dir.mkdir(parents=True, exist_ok=True)
        tmp = self._path.with_suffix(".tmp")
        tmp.write_text(
            json.dumps(dataclasses.asdict(params), ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        tmp.replace(self._path)

    def add_anchor_company(self, company: str) -> None:
        """Append a company to anchor_companies if not already present."""
        params = self.load()
        if params is None:
            return
        existing = {c.lower() for c in params.anchor_companies}
        if company.strip().lower() not in existing:
            params.anchor_companies.append(company.strip())
            self.save(params)

    def has_params(self) -> bool:
        return self._path.exists()
