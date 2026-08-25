import logging
from urllib.parse import parse_qs, urlparse

import httpx
from bs4 import BeautifulSoup

from app.core.config import get_settings
from app.engines.search.base import SearchHit, SearchProvider

logger = logging.getLogger(__name__)

_HTML_ENDPOINT = "https://html.duckduckgo.com/html/"


class DuckDuckGoSearchProvider(SearchProvider):
    """No-API-key search provider using DuckDuckGo's HTML (non-JS) results
    page. This is a reasonable default for an MVP with no search-API budget;
    ARCHITECTURE.md documents it as swappable, not a permanent production
    choice — a high-volume deployment should move to a paid search API with
    an SLA (Bing Web Search, Serper, Tavily, Google Programmable Search)."""

    async def search(self, query: str, *, max_results: int) -> list[SearchHit]:
        settings = get_settings()
        headers = {"User-Agent": settings.crawler_user_agent}
        async with httpx.AsyncClient(
            headers=headers, timeout=settings.crawler_request_timeout_seconds
        ) as client:
            try:
                response = await client.post(_HTML_ENDPOINT, data={"q": query})
                response.raise_for_status()
            except httpx.HTTPError as exc:
                logger.warning("search provider request failed: %s", exc)
                return []

        soup = BeautifulSoup(response.text, "lxml")
        hits: list[SearchHit] = []
        for result in soup.select("div.result"):
            link = result.select_one("a.result__a")
            if link is None or not link.get("href"):
                continue
            url = _unwrap_redirect(link["href"])
            if not url:
                continue
            title = link.get_text(strip=True)
            snippet_el = result.select_one(".result__snippet")
            snippet = snippet_el.get_text(strip=True) if snippet_el else ""
            hits.append(SearchHit(url=url, title=title, snippet=snippet))
            if len(hits) >= max_results:
                break
        return hits


def _unwrap_redirect(href: str) -> str | None:
    """DuckDuckGo's HTML results link through /l/?uddg=<encoded target>."""
    parsed = urlparse(href)
    if parsed.path == "/l/":
        target = parse_qs(parsed.query).get("uddg")
        return target[0] if target else None
    if parsed.scheme in ("http", "https"):
        return href
    return None
