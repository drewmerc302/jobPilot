import logging
import re
from datetime import datetime, timezone

import httpx
from tenacity import (
    retry,
    retry_if_exception_type,
    stop_after_attempt,
    wait_exponential,
)

from jobpilot.fetch_description import html_to_text
from jobpilot.scrapers.base import BaseScraper, RawJob

logger = logging.getLogger(__name__)

LEVER_API = "https://api.lever.co/v0/postings"

_http_retry = retry(
    stop=stop_after_attempt(3),
    wait=wait_exponential(multiplier=1, min=2, max=10),
    retry=retry_if_exception_type((httpx.HTTPError, httpx.TimeoutException)),
    reraise=True,
)


def _slugify(name: str) -> str:
    """Generate Lever slug variants: lowercase with no spaces, then with hyphens."""
    slug = name.lower().strip()
    slug = re.sub(r"[^a-z0-9\s-]", "", slug)
    return slug


def _slug_variants(company: str) -> list[str]:
    """Return candidate slugs to try against the Lever API."""
    base = _slugify(company)
    variants: list[str] = []
    # No spaces variant (e.g. "toptal")
    no_spaces = re.sub(r"\s+", "", base)
    if no_spaces:
        variants.append(no_spaces)
    # Hyphenated variant (e.g. "palo-alto-networks")
    hyphenated = re.sub(r"\s+", "-", base).strip("-")
    hyphenated = re.sub(r"-+", "-", hyphenated)
    if hyphenated and hyphenated != no_spaces:
        variants.append(hyphenated)
    return variants


class LeverProbeError(Exception):
    """Server-side issue (5xx, timeout, connection) — distinct from a 404."""


def probe_lever(company_name: str) -> "LeverScraper | None":
    """Try slug variants against the Lever API.

    Returns a LeverScraper if the board exists, None if all variants 404.
    Raises LeverProbeError on 5xx/timeout (stops trying further variants).
    """
    slugs = _slug_variants(company_name)
    if not slugs:
        return None

    for slug in slugs:
        url = f"{LEVER_API}/{slug}?mode=json"
        try:
            resp = httpx.get(url, timeout=5, headers={"User-Agent": "jobPilot/1.0"})
        except (httpx.TimeoutException, httpx.HTTPError) as exc:
            raise LeverProbeError(
                f"Lever probe network error for {company_name!r}: {exc}"
            ) from exc

        if resp.status_code == 404:
            logger.debug(
                "Lever board not found: %r (slug=%r) — trying next variant",
                company_name,
                slug,
            )
            continue
        if resp.status_code >= 500:
            raise LeverProbeError(f"Lever {resp.status_code} for {company_name!r}")
        if resp.status_code == 200:
            try:
                payload = resp.json()
            except ValueError as exc:
                raise LeverProbeError(
                    f"Lever non-JSON 200 for {company_name!r}: {exc}"
                ) from exc
            # Lever returns a JSON array; empty array means board exists but no jobs
            if isinstance(payload, list):
                logger.info("Lever board found: %r (slug=%r)", company_name, slug)
                return LeverScraper(slug=slug, company_name=company_name)
            return None
        # Other 4xx — treat as transient
        if 400 <= resp.status_code < 500:
            raise LeverProbeError(f"Lever {resp.status_code} for {company_name!r}")

    # All slugs returned 404
    return None


class LeverScraper(BaseScraper):
    source = "lever"
    tracks_full_company_listing = True

    def __init__(self, slug: str, company_name: str):
        self.slug = slug
        self.company_name = company_name

    def fetch_jobs(self) -> list[RawJob]:
        url = f"{LEVER_API}/{self.slug}?mode=json"
        try:
            resp = self._fetch_with_retry(url)
            return self._parse_response(resp.json())
        except Exception as exc:
            logger.error(f"Lever fetch failed for {self.company_name!r}: {exc}")
            return []

    @_http_retry
    def _fetch_with_retry(self, url: str) -> httpx.Response:
        resp = httpx.get(url, timeout=30, headers={"User-Agent": "jobPilot/1.0"})
        resp.raise_for_status()
        return resp

    def _parse_response(self, data: list) -> list[RawJob]:
        now = datetime.now(timezone.utc)
        jobs: list[RawJob] = []
        for item in data:
            categories = item.get("categories") or {}
            location = categories.get("location")
            department = categories.get("department")
            # Build description from descriptionPlain + lists content
            desc_parts: list[str] = []
            if item.get("descriptionPlain"):
                desc_parts.append(item["descriptionPlain"])
            for section in item.get("lists") or []:
                if section.get("text"):
                    desc_parts.append(f"\n{section['text']}")
                if section.get("content"):
                    desc_parts.append(html_to_text(section["content"]))
            if item.get("additionalPlain"):
                desc_parts.append(item["additionalPlain"])
            description = "\n".join(desc_parts).strip() or None

            jobs.append(
                RawJob(
                    external_id=item["id"],
                    company=self.company_name,
                    title=item.get("text") or "Untitled",
                    url=item.get("hostedUrl")
                    or f"https://jobs.lever.co/{self.slug}/{item['id']}",
                    location=location,
                    remote=self._is_remote(item),
                    salary=self._extract_salary(item),
                    description=description,
                    department=department,
                    seniority=None,
                    scraped_at=now,
                )
            )
        return jobs

    def _is_remote(self, item: dict) -> bool | None:
        workplace = item.get("workplaceType", "")
        if workplace == "remote":
            return True
        loc = ((item.get("categories") or {}).get("location") or "").lower()
        if "remote" in loc:
            return True
        return None

    def _extract_salary(self, item: dict) -> str | None:
        """Try to pull salary from additionalPlain or descriptionPlain."""
        for field in ("additionalPlain", "descriptionPlain"):
            text = item.get(field) or ""
            for pattern in [
                r"\$[\d,]+\s*[-–]\s*\$[\d,]+",
                r"\$[\d,]+(?:\.\d{2})?(?:\s*(?:to|[-–])\s*\$[\d,]+(?:\.\d{2})?)?",
            ]:
                m = re.search(pattern, text)
                if m:
                    return m.group(0)
        return None
