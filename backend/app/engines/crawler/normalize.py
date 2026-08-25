"""URL normalization — the first, cheapest layer of AUDIT_BPO_CRM.md's
Phase 4 dedup work. Two URLs that only differ by a tracking parameter or a
trailing slash are the same page; treating them as distinct candidates
wastes a crawl-budget slot and can make the same page show up twice in
results. This is deliberately conservative: it only strips parameters that
are *known* tracking noise (never a parameter that could change what the
server actually returns, like `?page=2` or `?id=42`) and never touches the
path's case, since path case is server-defined and can be meaningful.
"""

from urllib.parse import parse_qsl, urlencode, urlparse, urlunparse

# Common analytics/attribution parameters that never change page content.
_TRACKING_PARAMS = {
    "utm_source",
    "utm_medium",
    "utm_campaign",
    "utm_term",
    "utm_content",
    "utm_id",
    "fbclid",
    "gclid",
    "msclkid",
    "mc_cid",
    "mc_eid",
    "ref",
    "referrer",
}


def normalize_url(url: str) -> str:
    """Returns a canonical form of `url` suitable as a dedup key — not
    necessarily a URL you'd fetch (query params are still valid to send),
    just a stable identity for "is this the same page as one we've already
    queued or crawled?"."""
    parsed = urlparse(url)

    scheme = parsed.scheme.lower()
    netloc = parsed.netloc.lower()

    path = parsed.path
    if len(path) > 1 and path.endswith("/"):
        path = path.rstrip("/")

    query_pairs = parse_qsl(parsed.query, keep_blank_values=True)
    kept_params = sorted((k, v) for k, v in query_pairs if k not in _TRACKING_PARAMS)
    query = urlencode(kept_params)

    return urlunparse((scheme, netloc, path, "", query, ""))
