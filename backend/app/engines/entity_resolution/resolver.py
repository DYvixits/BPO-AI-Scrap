"""Entity Resolution Engine (AUDIT_BPO_CRM.md Phase 5): groups crawled
pages that refer to the same real-world company into one Company entity,
instead of surfacing every crawled page as an unrelated flat result.

Two-step, disclosed heuristic — no ML, no fuzzy string similarity beyond
exact match on a normalized name. This is a deliberately strict choice:
false merges are worse for a CRM feed than false splits (merging two
unrelated companies pollutes a customer's data; failing to merge two
pages of the same company just means one extra row to review), so this
resolver only merges pages when it has a real signal to point at, never a
"looks similar" guess.

1. Every page from the same registrable domain is the same company — this
   is already guaranteed by construction (the crawler only follows
   same-domain links, see crawler/links.py), so this step is just
   grouping, not resolution.
2. Domain-groups get merged into one company if their best-guess company
   *names* (from JSON-LD, then Open Graph site name, then title, in that
   preference order — the same "most structured signal first" pattern as
   extraction/structured.py) are identical after normalization
   (lowercased, legal-suffix-stripped, punctuation-stripped). This is the
   actual cross-source resolution — e.g. a company's own site and its
   Crunchbase profile, discovered via two different search hits, get
   recognized as the same company.

`match_confidence` is 1.0 for a single-domain company (nothing to
disambiguate) and 0.7 when pages from different domains were merged on a
name match alone — a disclosed number, not a verified claim (see
SECURITY.md on never fabricating confidence).
"""

import re
from dataclasses import dataclass

_LEGAL_SUFFIXES = {
    "incorporated",
    "inc",
    "corporation",
    "corp",
    "limited",
    "ltd",
    "llc",
    "gmbh",
    "sa",
    "srl",
    "plc",
    "co",
    "group",
    "holdings",
}
_ORG_TYPE_HINTS = ("organization", "corporation", "localbusiness")
_SEPARATOR_RE = re.compile(r"\s*[|\-–—:]\s*")  # noqa: RUF001 — real en/em dashes in titles
_NON_ALNUM_RE = re.compile(r"[^a-z0-9\s]")
_WHITESPACE_RE = re.compile(r"\s+")


@dataclass(frozen=True, slots=True)
class ResolvablePage:
    url: str
    domain: str
    title: str | None
    structured_data: dict


@dataclass(frozen=True, slots=True)
class AliasRecord:
    alias_type: str  # "name" | "domain"
    value: str
    source_url: str


@dataclass(frozen=True, slots=True)
class ResolvedCompany:
    canonical_name: str
    primary_domain: str
    description: str | None
    match_confidence: float
    member_urls: list[str]
    aliases: list[AliasRecord]


def _registrable_domain(domain: str) -> str:
    host = domain.split(":")[0].lower()
    return host[4:] if host.startswith("www.") else host


def normalize_company_name(name: str) -> str:
    """Canonical form used only for equality comparison during resolution
    — never displayed. Strips punctuation, common legal suffixes (Inc,
    Ltd, GmbH, ...), and collapses whitespace/case, so 'Acme, Inc.' and
    'ACME Incorporated' compare equal."""
    lowered = name.lower().strip()
    no_punct = _NON_ALNUM_RE.sub(" ", lowered)
    words = [w for w in _WHITESPACE_RE.split(no_punct.strip()) if w]
    while words and words[-1] in _LEGAL_SUFFIXES:
        words = words[:-1]
    return " ".join(words)


def _org_name_from_json_ld(json_ld: list[dict]) -> str | None:
    for obj in json_ld:
        obj_type = obj.get("@type")
        types = obj_type if isinstance(obj_type, list) else [obj_type]
        is_org = any(
            isinstance(t, str) and any(hint in t.lower() for hint in _ORG_TYPE_HINTS) for t in types
        )
        if is_org:
            name = obj.get("name")
            if isinstance(name, str) and name.strip():
                return name.strip()
    return None


def _first_segment(text: str) -> str:
    return _SEPARATOR_RE.split(text.strip(), maxsplit=1)[0].strip()


def _candidate_name(page: ResolvablePage) -> str | None:
    """Best-guess company name for one page, cheapest/most-authoritative
    signal first."""
    json_ld = page.structured_data.get("json_ld") or []
    if name := _org_name_from_json_ld(json_ld):
        return name
    if site_name := page.structured_data.get("og_site_name"):
        return site_name.strip()
    if og_title := page.structured_data.get("og_title"):
        return _first_segment(og_title)
    if page.title:
        return _first_segment(page.title)
    return None


def _fallback_name_from_domain(domain: str) -> str:
    root = domain.split(".")[0]
    return root.replace("-", " ").title()


def resolve_companies(pages: list[ResolvablePage]) -> list[ResolvedCompany]:
    """Groups `pages` into resolved companies. Pages with no domain are
    skipped (nothing to group them by)."""
    domain_groups: dict[str, list[ResolvablePage]] = {}
    for page in pages:
        domain = _registrable_domain(page.domain)
        if not domain:
            continue
        domain_groups.setdefault(domain, []).append(page)

    # Per-domain: pick a canonical name + a description + collect every
    # distinct name literally seen on that domain's pages (alias trail).
    domain_canonical: dict[str, str] = {}
    domain_description: dict[str, str | None] = {}
    domain_aliases: dict[str, list[AliasRecord]] = {}
    for domain, domain_pages in domain_groups.items():
        seen_names: dict[str, str] = {}  # normalized -> first literal form encountered
        description: str | None = None
        aliases: list[AliasRecord] = []
        for page in domain_pages:
            if name := _candidate_name(page):
                normalized = normalize_company_name(name)
                if normalized and normalized not in seen_names:
                    seen_names[normalized] = name
                    aliases.append(AliasRecord("name", name, page.url))
            if description is None:
                description = page.structured_data.get(
                    "meta_description"
                ) or page.structured_data.get("og_description")
        canonical = next(iter(seen_names.values()), None) or _fallback_name_from_domain(domain)
        aliases.append(AliasRecord("domain", domain, domain_pages[0].url))
        domain_canonical[domain] = canonical
        domain_description[domain] = description
        domain_aliases[domain] = aliases

    # Merge domain groups whose canonical names match after normalization.
    merged: dict[str, list[str]] = {}
    for domain, canonical in domain_canonical.items():
        merged.setdefault(normalize_company_name(canonical), []).append(domain)

    companies: list[ResolvedCompany] = []
    for domains in merged.values():
        primary_domain = min(domains, key=len)
        description = next((domain_description[d] for d in domains if domain_description[d]), None)
        all_aliases: list[AliasRecord] = []
        member_urls: list[str] = []
        for domain in domains:
            all_aliases.extend(domain_aliases[domain])
            member_urls.extend(p.url for p in domain_groups[domain])
        companies.append(
            ResolvedCompany(
                canonical_name=domain_canonical[primary_domain],
                primary_domain=primary_domain,
                description=description,
                match_confidence=1.0 if len(domains) == 1 else 0.7,
                member_urls=member_urls,
                aliases=all_aliases,
            )
        )
    return companies
