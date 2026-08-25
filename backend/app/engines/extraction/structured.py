"""A second extraction pass alongside trafilatura's main-content text
(content.py) — AUDIT_BPO_CRM.md's Phase 4 "multi-pass extraction". Pulls
structured signals a page's markup already declares rather than trying to
re-derive them from prose: JSON-LD (schema.org), Open Graph / meta tags,
and plain contact info (email/phone) visible in the page text. Every field
is either directly present in the markup or a regex match against visible
text — nothing here is inferred or guessed, matching this codebase's rule
against fabricating data that wasn't actually found.
"""

import json
import re
from dataclasses import dataclass, field

from bs4 import BeautifulSoup

_EMAIL_RE = re.compile(r"[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}")
# Deliberately conservative: requires at least 7 digits total so it doesn't
# match years, prices, or other short numbers that happen to contain
# separators — real-world phone numbers vary too much in format to fully
# validate with a regex, so this only aims to reduce false positives, not
# eliminate them (never surfaced as "verified", see SECURITY.md).
_PHONE_RE = re.compile(r"(?:\+\d{1,3}[\s.-]?)?(?:\(\d{2,4}\)[\s.-]?)?\d[\d\s.-]{6,14}\d")
_MAX_ITEMS = 10


@dataclass(frozen=True, slots=True)
class StructuredData:
    json_ld: list[dict] = field(default_factory=list)
    meta_description: str | None = None
    og_title: str | None = None
    og_description: str | None = None
    og_site_name: str | None = None
    emails: list[str] = field(default_factory=list)
    phones: list[str] = field(default_factory=list)

    def as_dict(self) -> dict:
        return {
            "json_ld": self.json_ld,
            "meta_description": self.meta_description,
            "og_title": self.og_title,
            "og_description": self.og_description,
            "og_site_name": self.og_site_name,
            "emails": self.emails,
            "phones": self.phones,
        }


def _parse_json_ld(soup: BeautifulSoup) -> list[dict]:
    objects: list[dict] = []
    for tag in soup.find_all("script", type="application/ld+json"):
        if not tag.string:
            continue
        try:
            parsed = json.loads(tag.string)
        except (json.JSONDecodeError, TypeError):
            continue
        candidates = parsed if isinstance(parsed, list) else [parsed]
        for candidate in candidates:
            if isinstance(candidate, dict):
                objects.append(candidate)
            if len(objects) >= _MAX_ITEMS:
                return objects
    return objects


def _meta_content(
    soup: BeautifulSoup, *, name: str | None = None, prop: str | None = None
) -> str | None:
    attrs = {"name": name} if name else {"property": prop}
    tag = soup.find("meta", attrs=attrs)
    if tag and tag.get("content"):
        return tag["content"].strip() or None
    return None


def extract_structured_data(html: str, *, url: str) -> StructuredData:
    soup = BeautifulSoup(html, "lxml")

    visible_text = soup.get_text(" ", strip=True)
    emails = _dedupe_ordered(_EMAIL_RE.findall(visible_text))[:_MAX_ITEMS]
    phones = _dedupe_ordered(m.strip() for m in _PHONE_RE.findall(visible_text))[:_MAX_ITEMS]

    return StructuredData(
        json_ld=_parse_json_ld(soup),
        meta_description=_meta_content(soup, name="description"),
        og_title=_meta_content(soup, prop="og:title"),
        og_description=_meta_content(soup, prop="og:description"),
        og_site_name=_meta_content(soup, prop="og:site_name"),
        emails=emails,
        phones=phones,
    )


def _dedupe_ordered(items) -> list[str]:
    seen: set[str] = set()
    result: list[str] = []
    for item in items:
        if item not in seen:
            seen.add(item)
            result.append(item)
    return result
