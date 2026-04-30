"""Lazy full-description fetcher for jobs stored with only a snippet."""

import logging
import re
from html.parser import HTMLParser

import httpx

logger = logging.getLogger(__name__)

_SNIPPET_RE = re.compile(r"&[a-z#0-9]+;|<[a-z]", re.IGNORECASE)
_SKIP_TAGS = frozenset(
    {
        "script",
        "style",
        "nav",
        "header",
        "footer",
        "aside",
        "noscript",
        "iframe",
        "form",
    }
)
_BLOCK_TAGS = frozenset(
    {"p", "div", "li", "br", "h1", "h2", "h3", "h4", "h5", "h6", "tr", "td"}
)


class _TextExtractor(HTMLParser):
    def __init__(self):
        super().__init__()
        self._skip_depth = 0
        self._parts: list[str] = []

    def handle_starttag(self, tag, attrs):
        t = tag.lower()
        if t in _SKIP_TAGS:
            self._skip_depth += 1
        elif t in _BLOCK_TAGS and self._skip_depth == 0:
            self._parts.append("\n")

    def handle_endtag(self, tag):
        if tag.lower() in _SKIP_TAGS:
            self._skip_depth = max(0, self._skip_depth - 1)

    def handle_data(self, data):
        if self._skip_depth == 0 and data.strip():
            self._parts.append(data)

    def get_text(self) -> str:
        raw = "".join(self._parts)
        return re.sub(r"\n{3,}", "\n\n", re.sub(r"[ \t]{2,}", " ", raw)).strip()


def is_snippet(description: str | None, source: str | None = None) -> bool:
    """Return True if the stored description looks like a truncated HTML snippet.

    Sources that always provide full descriptions (e.g. Greenhouse) bypass the check.
    """
    if source == "greenhouse":
        return False
    if not description or len(description) < 400:
        return True
    return bool(_SNIPPET_RE.search(description))


def fetch_full_description(url: str) -> str | None:
    """GET the job listing page and return clean extracted text.

    Returns None if the fetch fails or the extracted text is too short to be useful.
    Falls open — callers should run analysis on the existing description if this returns None.
    """
    if "jooble.org" in url:
        logger.debug(
            f"Skipping Jooble URL (Cloudflare blocks server-side fetches): {url}"
        )
        return None

    try:
        with httpx.Client(timeout=15, follow_redirects=True) as client:
            resp = client.get(
                url,
                headers={
                    "User-Agent": (
                        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                        "AppleWebKit/537.36 (KHTML, like Gecko) "
                        "Chrome/124.0.0.0 Safari/537.36"
                    ),
                    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
                    "Accept-Language": "en-US,en;q=0.9",
                },
            )
        resp.raise_for_status()
    except Exception as exc:
        logger.warning(f"fetch_full_description failed for {url}: {exc}")
        return None

    extractor = _TextExtractor()
    try:
        extractor.feed(resp.text)
    except Exception as exc:
        logger.warning(f"HTML parse error for {url}: {exc}")
        return None

    text = extractor.get_text()
    if len(text) < 300:
        logger.debug(f"Extracted text too short ({len(text)} chars) for {url}")
        return None
    return text
