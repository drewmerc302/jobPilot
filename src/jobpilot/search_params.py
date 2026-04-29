from dataclasses import dataclass, field


@dataclass
class SearchParams:
    """Per-user search configuration. Replaces jobTracker's hardcoded EM/Yardley config.

    Populated by the FTUE wizard and persisted to DB. Passed as a parameter to
    filter and scraper steps — never baked into Config.

    NOTE (Phase 0 decision): resume_data is passed as dict to step functions rather
    than stored here. The storage contract (DB table vs flat file) is deferred to
    Phase 2 when the FastAPI wizard is built. All step functions accept
    resume_data: dict as an explicit parameter.
    """

    keywords: list[str] = field(default_factory=list)
    location: str = ""
    latitude: float | None = None
    longitude: float | None = None
    radius_miles: int = 25
    remote_ok: bool = True
    seniority: str | None = None
    anchor_companies: list[str] = field(default_factory=list)
