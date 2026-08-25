"""Heuristic natural-language -> ResearchObjective parser (master spec §4).

Keyword matching only — no LLM call (see objective.py's docstring for why).
Every match is recorded in `matched_keywords` so the result is always
explainable: "why did this get tagged fintech?" has a literal answer, not
a black-box one.
"""

import re

from app.engines.query_intelligence.keywords import (
    ATTRIBUTES,
    FRESHNESS_KEYWORDS,
    GEOGRAPHY,
    INDUSTRY,
    PERSON_ENTITY_KEYWORDS,
    SIGNALS,
)
from app.engines.query_intelligence.objective import ResearchObjective

_SIZE_MIN_RE = re.compile(r"(?:more than|over|above)\s+(\d+)\s*employees?", re.IGNORECASE)
_SIZE_MAX_RE = re.compile(r"(?:less than|under|fewer than)\s+(\d+)\s*employees?", re.IGNORECASE)
_SIZE_PLUS_RE = re.compile(r"(\d+)\s*\+\s*employees?", re.IGNORECASE)
_SIZE_RANGE_RE = re.compile(r"(\d+)\s*-\s*(\d+)\s*employees?", re.IGNORECASE)
# Allows up to 2 words between the number and the noun ("250 fintech
# companies", "250 Cameroonian fintech companies") — real phrasing almost
# always has an adjective in between, a bare "\d+\s+companies" match alone
# missed that case entirely (caught live against the running app, not by a
# unit test — see tests/test_query_intelligence.py for the regression case).
_RESULT_LIMIT_RE = re.compile(
    r"\b(\d{2,5})\s+(?:[a-z-]+\s+){0,2}(?:companies|leads|prospects|results|entreprises)\b",
    re.IGNORECASE,
)


def _match_keywords(text: str, table: dict[str, list[str]]) -> tuple[list[str], list[str]]:
    """Returns (canonical matches, literal words that matched) for a
    canonical->surface-forms table.

    Surface forms are checked longest-first: several entries have one form
    that's a substring of another for the same entry (e.g. "cameroon" is a
    substring of "cameroonian"), and checking short-to-long would always
    report the shorter, less specific form as the match even when the
    longer one is what's actually in the text.
    """
    matched_canonical: list[str] = []
    matched_words: list[str] = []
    for canonical, surface_forms in table.items():
        for form in sorted(surface_forms, key=len, reverse=True):
            if form in text:
                matched_canonical.append(canonical)
                matched_words.append(form)
                break
    return matched_canonical, matched_words


def parse_query(query: str) -> ResearchObjective:
    text = query.lower()
    matched_keywords: dict[str, list[str]] = {}

    geography, geo_words = _match_keywords(text, GEOGRAPHY)
    if geography:
        matched_keywords["geography"] = geo_words

    industry, industry_words = _match_keywords(text, INDUSTRY)
    if industry:
        matched_keywords["industry"] = industry_words

    signal_matches, signal_words = [], []
    for canonical, (surface_forms, _polarity) in SIGNALS.items():
        for form in surface_forms:
            if form in text:
                signal_matches.append(canonical)
                signal_words.append(form)
                break
    if signal_matches:
        matched_keywords["signals"] = signal_words

    attributes, attribute_words = _match_keywords(text, ATTRIBUTES)
    if attributes:
        matched_keywords["required_attributes"] = attribute_words

    target_entities = ["company"]
    person_words = [kw for kw in PERSON_ENTITY_KEYWORDS if kw in text]
    if person_words:
        target_entities.append("person")
        matched_keywords["target_entities"] = person_words

    freshness_words = [kw for kw in FRESHNESS_KEYWORDS if kw in text]
    freshness = "recent" if freshness_words else "any"
    if freshness_words:
        matched_keywords["freshness"] = freshness_words

    company_size_min: int | None = None
    company_size_max: int | None = None
    if match := _SIZE_RANGE_RE.search(text):
        company_size_min, company_size_max = int(match.group(1)), int(match.group(2))
        matched_keywords["company_size"] = [match.group(0)]
    elif match := _SIZE_PLUS_RE.search(text):
        company_size_min = int(match.group(1))
        matched_keywords["company_size"] = [match.group(0)]
    else:
        if match := _SIZE_MIN_RE.search(text):
            company_size_min = int(match.group(1))
            matched_keywords.setdefault("company_size", []).append(match.group(0))
        if match := _SIZE_MAX_RE.search(text):
            company_size_max = int(match.group(1))
            matched_keywords.setdefault("company_size", []).append(match.group(0))

    return ResearchObjective(
        target_entities=target_entities,
        geography=geography,
        industry=industry,
        company_size_min=company_size_min,
        company_size_max=company_size_max,
        required_attributes=attributes,
        signals=signal_matches,
        freshness=freshness,
        matched_keywords=matched_keywords,
    )


def parse_result_limit(query: str) -> int | None:
    """Separate from parse_query's ResearchObjective — a result_limit found
    in the text is used by the orchestrator to override the mode's default
    result count, not stored as part of the objective itself."""
    match = _RESULT_LIMIT_RE.search(query.lower())
    return int(match.group(1)) if match else None
