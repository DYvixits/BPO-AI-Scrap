"""Goal-driven crawl prioritization (AUDIT_BPO_CRM.md's Phase 3): NextBestURL
scoring so the crawler visits the pages most likely to satisfy the research
objective first, plus an information-gain tracker so a job can stop once it
has actually learned what it was looking for instead of always spending its
full page budget crawling everything discovered.
"""

from dataclasses import dataclass

from app.engines.query_intelligence.keywords import ATTRIBUTES
from app.engines.query_intelligence.objective import ResearchObjective

# Canonical required-attribute -> the page-path/anchor-text words that tend
# to host it. Deliberately a *different* vocabulary than ATTRIBUTES' query
# surface forms (keywords.py): nobody's URL literally says "/ceo/", but
# "/about" or "/team" is usually where a CEO's name actually lives. Modest
# and extensible like the other keyword tables in this codebase, not
# exhaustive — see keywords.py's own docstring for the same tradeoff.
ATTRIBUTE_PAGE_SIGNALS: dict[str, list[str]] = {
    "ceo": ["team", "about", "leadership", "management", "founders"],
    "founders": ["team", "about", "founders", "our-story", "history"],
    "founded_year": ["about", "history", "our-story"],
    "employees": ["about", "team", "careers", "jobs"],
    "revenue": ["investors", "press", "news", "financials", "about"],
    "funding": ["investors", "press", "news"],
    "investors": ["investors", "press", "news"],
    "website": [],  # the homepage itself already satisfies this — no dedicated subpage to seek
}

_BASE_SCORE = 1.0
_ATTRIBUTE_SIGNAL_BONUS = 2.0
_DEPTH_DECAY = 0.6


@dataclass(frozen=True, slots=True)
class CrawlCandidate:
    url: str
    anchor_text: str
    depth: int


def score_candidate(
    *, url: str, anchor_text: str, objective: ResearchObjective, depth: int
) -> float:
    """Higher is more worth crawling next. Not a probability, not a
    verified-relevance claim — a disclosed, inspectable heuristic, exactly
    like every other score in this phase (see SECURITY.md / ARCHITECTURE.md
    §6 on never fabricating confidence). Depth-decayed so a same-domain
    link found three hops deep doesn't outrank a directly-discovered
    search-result page just because it happens to mention a keyword."""
    haystack = f"{url.lower()} {anchor_text.lower()}"
    score = _BASE_SCORE
    for attribute in objective.required_attributes:
        for signal in ATTRIBUTE_PAGE_SIGNALS.get(attribute, ()):
            if signal in haystack:
                score += _ATTRIBUTE_SIGNAL_BONUS
                break
    return score * (_DEPTH_DECAY**depth)


class InformationGainTracker:
    """Tracks which of the objective's `required_attributes` have actually
    been found in crawled page text so far, reusing the exact ATTRIBUTES
    keyword table the Query Intelligence Engine uses to *detect* those
    attributes in a query (query_intelligence/keywords.py) — one
    vocabulary spent both ways, not two that could silently drift apart.

    `enabled` is False when the objective didn't ask for anything specific:
    with no required_attributes there is nothing to measure gain against,
    so early stopping never applies and a crawl runs on its page budget
    alone — identical to this codebase's behavior before this phase.
    """

    def __init__(self, required_attributes: list[str]) -> None:
        self.required: set[str] = set(required_attributes)
        self.satisfied: set[str] = set()
        self.enabled = bool(self.required)

    def record_page(self, text: str | None) -> int:
        """Returns how many *new* required attributes this page satisfied."""
        if not self.enabled or not text:
            return 0
        haystack = text.lower()
        newly_satisfied: set[str] = set()
        for attribute in self.required - self.satisfied:
            for surface_form in ATTRIBUTES.get(attribute, ()):
                if surface_form in haystack:
                    newly_satisfied.add(attribute)
                    break
        self.satisfied |= newly_satisfied
        return len(newly_satisfied)

    @property
    def all_satisfied(self) -> bool:
        return self.enabled and self.satisfied == self.required
