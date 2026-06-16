"""Oracle HCM scraper: URL parsing, probe precedence, req parsing, and the
search-params persistence that keeps URL-resolved companies durable across
refreshes."""

import json
import sys
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from jobpilot.scrapers.oracle import (  # noqa: E402
    OracleScraper,
    _parse_oracle_url,
    probe_oracle,
)
from jobpilot.search_params import SearchParams  # noqa: E402
from jobpilot.state import SearchParamsStore  # noqa: E402

NOW = datetime(2026, 6, 16, tzinfo=timezone.utc)


# --- URL parsing -----------------------------------------------------------


def test_parse_url_with_explicit_site():
    url = "https://acme.fa.oraclecloud.com/hcmUI/CandidateExperience/en/sites/CX_2001/job/123"
    assert _parse_oracle_url(url) == ("acme", "CX_2001")


def test_parse_url_defaults_site_when_absent():
    assert _parse_oracle_url("https://acme.fa.oraclecloud.com/") == ("acme", "CX_1001")


def test_parse_url_rejects_non_oracle():
    assert _parse_oracle_url("https://boards.greenhouse.io/acme") is None
    assert _parse_oracle_url("") is None
    assert _parse_oracle_url("not a url") is None


# --- probe precedence ------------------------------------------------------


def test_probe_map_hit_by_name():
    s = probe_oracle("JPMorganChase")
    assert isinstance(s, OracleScraper)
    assert s.tenant == "jpmc"
    assert s.site_number == "CX_1001"


def test_probe_url_fallback_for_unknown_company():
    s = probe_oracle(
        "Some Bank",
        url="https://somebank.fa.oraclecloud.com/hcmUI/CandidateExperience/en/sites/CX_9/job/1",
    )
    assert isinstance(s, OracleScraper)
    assert s.tenant == "somebank"
    assert s.site_number == "CX_9"


def test_probe_returns_none_when_unresolvable():
    assert probe_oracle("Totally Unknown Co") is None
    assert probe_oracle("Totally Unknown Co", url="https://greenhouse.io/x") is None


def test_probe_threads_keywords_lowercased():
    s = probe_oracle("JPMorganChase", keywords=["Engineering Manager", "Director"])
    assert s.keyword_patterns == ["engineering manager", "director"]


# --- req parsing -----------------------------------------------------------


def _scraper():
    return OracleScraper(company_name="JPMorganChase", tenant="jpmc")


def test_parse_req_full():
    job = _scraper()._parse_req(
        {
            "Id": "210012345",
            "Title": "Engineering Manager, Payments",
            "PrimaryLocation": "New York, NY",
            "PrimaryLocationCountry": "US",
            "WorkplaceTypeCode": "REMOTE",
            "Department": "Technology",
            "ManagerLevel": "M3",
            "ExternalDescriptionStr": "Lead a team. Comp $180,000 - $220,000.",
        },
        NOW,
    )
    assert job.external_id == "210012345"
    assert job.title == "Engineering Manager, Payments"
    assert (
        job.url
        == "https://jpmc.fa.oraclecloud.com/hcmUI/CandidateExperience/en/sites/CX_1001/job/210012345"
    )
    assert job.remote is True
    assert job.department == "Technology"
    assert job.seniority == "M3"
    assert job.salary == "$180,000 - $220,000"
    assert "Lead a team" in job.description


def test_extract_remote_codes():
    s = _scraper()
    assert s._extract_remote({"WorkplaceTypeCode": "REMOTE"}) is True
    assert s._extract_remote({"WorkplaceTypeCode": "ONSITE"}) is False
    assert s._extract_remote({"WorkplaceTypeCode": "HYBRID"}) is False
    assert s._extract_remote({"PrimaryLocation": "Remote - US"}) is True
    assert s._extract_remote({"PrimaryLocation": "New York, NY"}) is None


def test_title_prefilter():
    s = OracleScraper("X", "x", keyword_patterns=["engineering manager"])
    assert s._title_matches("Senior Engineering Manager") is True
    assert s._title_matches("Data Scientist") is False
    # no patterns -> everything passes (downstream filter does the matching)
    assert OracleScraper("X", "x")._title_matches("anything") is True


def test_empty_keyword_search_omits_finder_keyword():
    # keyword_search defaults to "" so the listings finder must not emit keyword=
    s = _scraper()
    assert s.keyword_search == ""


# --- durable overrides -----------------------------------------------------


def test_search_params_oracle_overrides_roundtrip(tmp_path):
    store = SearchParamsStore(tmp_path)
    store.save(SearchParams(anchor_companies=["Acme"]))
    store.add_oracle_override("Acme", "https://acme.fa.oraclecloud.com/")
    loaded = store.load()
    assert loaded.oracle_overrides == {"acme": "https://acme.fa.oraclecloud.com/"}


def test_search_params_loads_legacy_json_without_overrides(tmp_path):
    # A search_params.json written before oracle_overrides existed must still load.
    path = tmp_path / "search_params.json"
    path.write_text(
        json.dumps({"keywords": ["em"], "anchor_companies": ["Acme"]}),
        encoding="utf-8",
    )
    loaded = SearchParamsStore(tmp_path).load()
    assert loaded.oracle_overrides == {}
    assert loaded.anchor_companies == ["Acme"]
