"""Verification Engine (AUDIT_BPO_CRM.md Phase 6): a disclosed,
multi-source confidence score for each resolved Company, replacing "we
found some pages" with "here's how much independent evidence exists, and
how fresh it is."

This does NOT implement the master spec's full Truth Engine. That needs
claim-level extraction (subject-predicate-object facts, e.g. "founded_year:
2021") to detect agreement/contradiction across sources, and claim
extraction was never built in this codebase (AUDIT_BPO_CRM.md's Evidence
Engine row said "MISSING — no Claim/Evidence tables yet"; this phase adds
an Evidence table, but it records *pages*, not *claims*). What's computed
here operates one level up, at the company/source level, using only real,
literal signals already produced by Entity Resolution and the crawler:

- source_count / source_diversity: how many crawled pages, from how many
  distinct domains, resolved to this company. A domain only counts as
  "independent" in the sense that the crawler discovered it as a separate
  site — not vetted for editorial independence (e.g. two syndicated
  copies of the same press release on two domains still count as two).
- freshness_score: how recently the most recently crawled piece of
  evidence was fetched, decaying linearly to 0 past OUTDATED_DAYS.
- evidence_completeness: fraction of evidence entries that actually carry
  a text excerpt (title or extracted text), vs. a bare URL with nothing
  extracted.

`status` covers 5 of the master spec's 7 Truth Engine states —
UNVERIFIABLE, UNCERTAIN, CORROBORATED, VERIFIED, OUTDATED — chosen because
each is computable from source count/diversity/freshness alone. PROBABLE
and CONTRADICTED are not computed: both require comparing what different
sources actually *claim*, which needs the claim extraction this phase
doesn't build. A company is never labeled VERIFIED without at least
`VERIFIED_MIN_DOMAINS` independent domains, per master spec §98's rule
against claiming "Verified" without real multi-source corroboration.
"""

from dataclasses import dataclass
from datetime import UTC, datetime
from enum import StrEnum

# Evidence older than this no longer supports any status but OUTDATED,
# regardless of how many domains it came from — a disclosed cutoff, not a
# derived constant.
OUTDATED_DAYS = 180
# No freshness penalty at all inside this window.
_FRESHNESS_GRACE_DAYS = 30
VERIFIED_MIN_DOMAINS = 3
CORROBORATED_MIN_DOMAINS = 2


class TruthStatus(StrEnum):
    UNVERIFIABLE = "unverifiable"
    UNCERTAIN = "uncertain"
    CORROBORATED = "corroborated"
    VERIFIED = "verified"
    OUTDATED = "outdated"


@dataclass(frozen=True, slots=True)
class EvidenceInput:
    domain: str
    source_url: str
    excerpt: str | None
    crawled_at: datetime


@dataclass(frozen=True, slots=True)
class ConfidenceResult:
    status: TruthStatus
    source_count: int
    source_diversity: int
    freshness_score: float
    evidence_completeness: float
    overall_score: float


def _age_days(now: datetime, crawled_at: datetime) -> float:
    # All timestamps in this app are UTC, but SQLite (unlike Postgres)
    # silently drops tzinfo from a DateTime(timezone=True) column on
    # read-back — a real cross-dialect gap, not a hypothetical one (see
    # tests/test_verification_pipeline.py, which caught this against the
    # SQLite-backed test suite). Treat a naive value as UTC rather than
    # let the subtraction below raise.
    if crawled_at.tzinfo is None:
        crawled_at = crawled_at.replace(tzinfo=UTC)
    if now.tzinfo is None:
        now = now.replace(tzinfo=UTC)
    return (now - crawled_at).total_seconds() / 86400


def _freshness_score(age_days: float) -> float:
    if age_days <= _FRESHNESS_GRACE_DAYS:
        return 1.0
    if age_days >= OUTDATED_DAYS:
        return 0.0
    span = OUTDATED_DAYS - _FRESHNESS_GRACE_DAYS
    return round(1.0 - (age_days - _FRESHNESS_GRACE_DAYS) / span, 2)


def compute_confidence(evidence: list[EvidenceInput], *, now: datetime) -> ConfidenceResult:
    if not evidence:
        return ConfidenceResult(
            status=TruthStatus.UNVERIFIABLE,
            source_count=0,
            source_diversity=0,
            freshness_score=0.0,
            evidence_completeness=0.0,
            overall_score=0.0,
        )

    source_count = len(evidence)
    source_diversity = len({e.domain for e in evidence})

    # The freshest piece of evidence sets the freshness score — one recent
    # source is enough to say "this isn't stale," even if older evidence
    # also exists.
    youngest_age_days = min(_age_days(now, e.crawled_at) for e in evidence)
    freshness_score = _freshness_score(youngest_age_days)

    with_excerpt = sum(1 for e in evidence if e.excerpt and e.excerpt.strip())
    evidence_completeness = round(with_excerpt / source_count, 2)

    if youngest_age_days >= OUTDATED_DAYS:
        status = TruthStatus.OUTDATED
    elif source_diversity >= VERIFIED_MIN_DOMAINS:
        status = TruthStatus.VERIFIED
    elif source_diversity >= CORROBORATED_MIN_DOMAINS:
        status = TruthStatus.CORROBORATED
    else:
        status = TruthStatus.UNCERTAIN

    diversity_score = min(source_diversity / VERIFIED_MIN_DOMAINS, 1.0)
    overall_score = round((diversity_score + freshness_score + evidence_completeness) / 3, 2)

    return ConfidenceResult(
        status=status,
        source_count=source_count,
        source_diversity=source_diversity,
        freshness_score=freshness_score,
        evidence_completeness=evidence_completeness,
        overall_score=overall_score,
    )
