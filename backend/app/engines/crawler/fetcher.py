import hashlib
import logging
from dataclasses import dataclass

import httpx

from app.core.config import get_settings
from app.engines.crawler.ssrf_guard import UnsafeURLError, assert_safe_url

logger = logging.getLogger(__name__)

_MAX_REDIRECTS = 5


@dataclass(frozen=True, slots=True)
class FetchResult:
    url: str
    http_status: int | None
    html: str | None
    content_hash: str | None
    error: str | None


class PageFetcher:
    """HTTP-only fetcher (Phase 1-3). Phase 4 adds a Playwright-backed
    implementation behind the same interface, selected adaptively per URL
    (ARCHITECTURE.md §7)."""

    def __init__(self) -> None:
        self._settings = get_settings()

    async def fetch(self, url: str) -> FetchResult:
        try:
            assert_safe_url(url)
        except UnsafeURLError as exc:
            return FetchResult(
                url=url, http_status=None, html=None, content_hash=None, error=str(exc)
            )

        headers = {"User-Agent": self._settings.crawler_user_agent}
        current_url = url

        async with httpx.AsyncClient(
            headers=headers,
            timeout=self._settings.crawler_request_timeout_seconds,
            follow_redirects=False,
        ) as client:
            for _ in range(_MAX_REDIRECTS + 1):
                try:
                    async with client.stream("GET", current_url) as response:
                        if response.is_redirect:
                            next_url = (
                                str(response.next_request.url) if response.next_request else None
                            )
                            if not next_url:
                                return FetchResult(
                                    url=current_url,
                                    http_status=response.status_code,
                                    html=None,
                                    content_hash=None,
                                    error="Redirect with no target",
                                )
                            try:
                                assert_safe_url(next_url)
                            except UnsafeURLError as exc:
                                return FetchResult(
                                    url=current_url,
                                    http_status=response.status_code,
                                    html=None,
                                    content_hash=None,
                                    error=f"Redirect target rejected: {exc}",
                                )
                            current_url = next_url
                            continue

                        body = await _read_capped(
                            response, self._settings.crawler_max_response_bytes
                        )
                        return FetchResult(
                            url=current_url,
                            http_status=response.status_code,
                            html=body,
                            content_hash=hashlib.sha256(
                                body.encode("utf-8", errors="ignore")
                            ).hexdigest()
                            if body
                            else None,
                            error=None,
                        )
                except httpx.HTTPError as exc:
                    logger.info("fetch failed for %s: %s", current_url, exc)
                    return FetchResult(
                        url=current_url,
                        http_status=None,
                        html=None,
                        content_hash=None,
                        error=str(exc),
                    )

        return FetchResult(
            url=current_url,
            http_status=None,
            html=None,
            content_hash=None,
            error="Too many redirects",
        )


async def _read_capped(response: httpx.Response, max_bytes: int) -> str:
    chunks: list[bytes] = []
    total = 0
    async for chunk in response.aiter_bytes():
        total += len(chunk)
        if total > max_bytes:
            break
        chunks.append(chunk)
    return b"".join(chunks).decode(response.encoding or "utf-8", errors="ignore")
