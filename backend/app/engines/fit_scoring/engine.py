"""Fit Scoring Engine (AUDIT_BPO_CRM.md Phase 8): how well a resolved
Company's own crawled pages actually satisfy the criteria the user's
query asked for — industry, geography, required_attributes — reusing the
exact `GEOGRAPHY`/`INDUSTRY`/`ATTRIBUTES` keyword tables Query
Intelligence used to parse those criteria out of the query in the first
place (the same "one vocabulary, spent both ways" pattern
`crawler/prioritization.py::InformationGainTracker` already established
for `required_attributes` — this just extends it to industry/geography
and moves it from "did the crawl find this" to "does this specific
company's evidence show this").

Deliberately not scored: `company_size_min`/`company_size_max` (no
headcount data is ever extracted from crawled pages in this codebase — a
disclosed gap, not an oversight) and `target_entities`/`signals`/
`freshness` (freshness is Verification's job, signals are the Commercial
Signal Engine's — Fit is specifically "does this company match the
stated industry/geography/attribute criteria," nothing else).

`score` is `matched / (matched + unmatched)` — `None`, not `0.0`, when
the objective declared zero checkable criteria (a fully generic query
like "find some companies"): there is nothing to compute fit against, so
a numeric score would be fabricated, not computed. Callers (Opportunity
Scoring) are expected to treat `None` as "unknown," not "bad fit."
"""

from dataclasses import dataclass

from app.engines.query_intelligence.keywords import ATTRIBUTES, GEOGRAPHY, INDUSTRY
from app.engines.query_intelligence.objective import ResearchObjective


@dataclass(frozen=True, slots=True)
class FitResult:
    score: float | None
    matched_factors: list[str]
    unmatched_factors: list[str]


def _check(
    text: str, table: dict[str, list[str]], canonicals: list[str], prefix: str
) -> tuple[list[str], list[str]]:
    matched: list[str] = []
    unmatched: list[str] = []
    for canonical in canonicals:
        forms = table.get(canonical, [])
        label = f"{prefix}:{canonical}"
        if any(form in text for form in forms):
            matched.append(label)
        else:
            unmatched.append(label)
    return matched, unmatched


def compute_fit(objective: ResearchObjective, page_text: str | None) -> FitResult:
    text = (page_text or "").lower()

    industry_matched, industry_unmatched = _check(text, INDUSTRY, objective.industry, "industry")
    geo_matched, geo_unmatched = _check(text, GEOGRAPHY, objective.geography, "geography")
    attr_matched, attr_unmatched = _check(
        text, ATTRIBUTES, objective.required_attributes, "required_attribute"
    )

    matched = industry_matched + geo_matched + attr_matched
    unmatched = industry_unmatched + geo_unmatched + attr_unmatched
    total = len(matched) + len(unmatched)

    if total == 0:
        return FitResult(score=None, matched_factors=[], unmatched_factors=[])
    return FitResult(
        score=round(len(matched) / total, 2), matched_factors=matched, unmatched_factors=unmatched
    )
