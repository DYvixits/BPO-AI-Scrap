"""Commercial Signal Engine (AUDIT_BPO_CRM.md Phase 7): scans a resolved
company's crawled page text for the same disclosed keyword vocabulary the
Query Intelligence Engine already uses to parse a user's query
(`app/engines/query_intelligence/keywords.py::SIGNALS`) — reused here
rather than duplicated, since that module's own comment flagged it as
"recorded now so [Phase 7's Commercial Signal Engine] has a documented
starting vocabulary." A signal detected on a company's own pages (e.g. a
press release mentioning "raised $10M in Series A funding") is a much
stronger commercial trigger than the same word merely appearing in the
user's search query, so this is a genuinely new signal, not a repeat of
Query Intelligence's work.

Temporal decay: a signal's usefulness fades over time — a funding
announcement from three years ago says much less about "is this company
worth calling now" than one from last month. This codebase has no
reliable way to extract the *actual event date* from freeform page text
(real date extraction from prose is a much harder, error-prone problem
than keyword matching, and this phase doesn't attempt it — a disclosed
scope limit, not an oversight). Decay instead uses the crawled page's
fetch time as a proxy for "when we learned about this," the same
proxy-for-recency approach Phase 6's Verification Engine already
discloses for evidence freshness. `decayed_strength` is computed once, at
pipeline-completion time — same limitation as Verification's
`freshness_score` (see that module's REMAINING notes): it does not keep
decaying in the database as real time passes without a future re-run
(Phase 10 Monitoring's job).

Every signal detected here carries `base_weight` = 1.0, uniformly — this
phase deliberately does not decide that "funding" matters more than
"hiring" for a given tenant's sales motion. Per-signal-type weighting is
a scoring decision (master spec §56's per-tenant-configurable Opportunity
formula) that belongs to Phase 8's Intent Engine, which consumes these
rows; Phase 7's job is detecting and time-decaying, not prioritizing.
"""

from dataclasses import dataclass
from datetime import UTC, datetime
from enum import StrEnum

from app.engines.query_intelligence.keywords import SIGNALS

# Evidence older than this has fully decayed to zero strength — matches
# Verification Engine's OUTDATED_DAYS for consistency across the codebase,
# not a separately-derived number.
SIGNAL_DECAY_DAYS = 180
BASE_WEIGHT = 1.0
# Context captured on either side of a matched keyword, for a readable
# excerpt without pulling in the whole page.
_EXCERPT_RADIUS = 100


class CommercialSignalType(StrEnum):
    """Must stay in sync with `query_intelligence/keywords.py::SIGNALS`'s
    keys — enforced by test_commercial_signals.py, not by construction,
    since a Postgres enum's values must be static for Alembic, while
    SIGNALS is an ordinary importable dict."""

    HIRING = "hiring"
    EXPANSION = "expansion"
    FUNDING = "funding"
    ACQUISITION = "acquisition"
    LEADERSHIP_CHANGE = "leadership_change"
    PRODUCT_LAUNCH = "product_launch"
    DIGITAL_TRANSFORMATION = "digital_transformation"
    LAYOFFS = "layoffs"
    CLOSURE = "closure"


@dataclass(frozen=True, slots=True)
class DetectedSignal:
    signal_type: CommercialSignalType
    polarity: str
    matched_keyword: str
    excerpt: str


def _excerpt_around(text: str, index: int, keyword_len: int) -> str:
    start = max(0, index - _EXCERPT_RADIUS)
    end = min(len(text), index + keyword_len + _EXCERPT_RADIUS)
    return text[start:end].strip()


def detect_signals(text: str | None) -> list[DetectedSignal]:
    """At most one signal per type per call — the first matching surface
    form wins, same "first candidate wins" simplicity as
    entity_resolution/resolver.py's name selection. Call once per crawled
    page; a company with several pages mentioning funding gets several
    rows (one per page), which is the intended evidence trail, not a
    dedup bug."""
    if not text:
        return []
    lowered = text.lower()
    detected: list[DetectedSignal] = []
    for canonical, (surface_forms, polarity) in SIGNALS.items():
        for form in surface_forms:
            index = lowered.find(form)
            if index != -1:
                detected.append(
                    DetectedSignal(
                        signal_type=CommercialSignalType(canonical),
                        polarity=polarity,
                        matched_keyword=form,
                        excerpt=_excerpt_around(text, index, len(form)),
                    )
                )
                break
    return detected


def _age_days(now: datetime, then: datetime) -> float:
    # Same SQLite-vs-Postgres tzinfo gap documented in
    # engines/verification/engine.py::_age_days — duplicated rather than
    # imported cross-engine, since these two engines are otherwise
    # deliberately decoupled (see ARCHITECTURE.md's engine-per-concern
    # layout).
    if then.tzinfo is None:
        then = then.replace(tzinfo=UTC)
    if now.tzinfo is None:
        now = now.replace(tzinfo=UTC)
    return (now - then).total_seconds() / 86400


def decay_strength(base_weight: float, *, crawled_at: datetime, now: datetime) -> float:
    age_days = _age_days(now, crawled_at)
    if age_days <= 0:
        return round(base_weight, 2)
    if age_days >= SIGNAL_DECAY_DAYS:
        return 0.0
    return round(base_weight * (1.0 - age_days / SIGNAL_DECAY_DAYS), 2)
