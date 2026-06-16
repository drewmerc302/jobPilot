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
    remote_ok: bool = False
    seniority: str | None = None
    anchor_companies: list[str] = field(default_factory=list)
    # Oracle HCM has no slug→tenant convention, so a company resolved from a
    # pasted careers URL must persist that URL — otherwise the next full refresh
    # (which only has the company name) silently stops scraping it. Keyed by
    # lowercased company name → careers URL.
    oracle_overrides: dict[str, str] = field(default_factory=dict)
