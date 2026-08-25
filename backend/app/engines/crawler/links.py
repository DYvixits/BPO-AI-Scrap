"""Same-domain link discovery from a fetched page's HTML — the raw material
for goal-driven crawl prioritization (AUDIT_BPO_CRM.md's Phase 3: adaptive
strategy, NextBestURL). Phase 1-3's crawler never looked past the initial
search-result URLs; this lets the crawler follow promising same-domain
links (e.g. a company's homepage -> its /about or /team page) instead of
being limited to whatever a search engine's result snippet happened to
surface directly.

Deliberately same-domain only: cross-domain expansion is Source Discovery
territory (AUDIT_BPO_CRM.md Phase 2's still-open multi-provider item), not
link-following — a crawl that started on one company's site should not
wander off onto a news site it happens to link to.
"""

from dataclasses import dataclass
from urllib.parse import urldefrag, urljoin, urlparse

from bs4 import BeautifulSoup

_SKIP_SCHEMES = {"mailto", "tel", "javascript"}
_SKIP_EXTENSIONS = (
    ".pdf",
    ".jpg",
    ".jpeg",
    ".png",
    ".gif",
    ".svg",
    ".webp",
    ".zip",
    ".css",
    ".js",
    ".ico",
    ".mp4",
    ".mp3",
    ".woff",
    ".woff2",
)


@dataclass(frozen=True, slots=True)
class DiscoveredLink:
    url: str
    anchor_text: str


def _registrable_domain(netloc: str) -> str:
    # Crude but sufficient: strip a leading "www." so "www.acme.com" and
    # "acme.com" count as the same site. A real public-suffix-list lookup
    # is overkill for this phase's scope (no dependency on one exists yet
    # in this codebase) — a false "different site" here only costs a
    # missed link, it never widens what the SSRF guard (a separate,
    # independent check in fetcher.py) allows.
    host = netloc.split(":")[0].lower()
    return host[4:] if host.startswith("www.") else host


def extract_links(html: str, *, base_url: str) -> list[DiscoveredLink]:
    """Parses every `<a href>` in `html`, resolves it against `base_url`,
    and returns only same-registrable-domain, http(s), non-asset links —
    deduplicated by URL (fragment-stripped, since '#section' anchors on the
    same page aren't new pages to crawl)."""
    soup = BeautifulSoup(html, "lxml")
    base_domain = _registrable_domain(urlparse(base_url).netloc)

    seen: set[str] = set()
    links: list[DiscoveredLink] = []
    for tag in soup.find_all("a", href=True):
        href = tag["href"].strip()
        if not href or href.startswith("#"):
            continue

        absolute = urljoin(base_url, href)
        parsed = urlparse(absolute)
        if parsed.scheme in _SKIP_SCHEMES or parsed.scheme not in ("http", "https"):
            continue
        if parsed.path.lower().endswith(_SKIP_EXTENSIONS):
            continue
        if _registrable_domain(parsed.netloc) != base_domain:
            continue

        normalized, _fragment = urldefrag(absolute)
        if normalized in seen:
            continue
        seen.add(normalized)

        anchor_text = tag.get_text(strip=True)[:200]
        links.append(DiscoveredLink(url=normalized, anchor_text=anchor_text))

    return links
