from datetime import UTC, datetime, timedelta

from app.engines.verification.engine import (
    CORROBORATED_MIN_DOMAINS,
    OUTDATED_DAYS,
    VERIFIED_MIN_DOMAINS,
    EvidenceInput,
    TruthStatus,
    compute_confidence,
)

NOW = datetime(2026, 1, 1, tzinfo=UTC)


def _evidence(
    domain: str, *, age_days: float = 0, excerpt: str | None = "some text"
) -> EvidenceInput:
    return EvidenceInput(
        domain=domain,
        source_url=f"https://{domain}/",
        excerpt=excerpt,
        crawled_at=NOW - timedelta(days=age_days),
    )


def test_no_evidence_is_unverifiable():
    result = compute_confidence([], now=NOW)
    assert result.status == TruthStatus.UNVERIFIABLE
    assert result.source_count == 0
    assert result.source_diversity == 0
    assert result.overall_score == 0.0


def test_single_source_is_uncertain():
    result = compute_confidence([_evidence("acme.com")], now=NOW)
    assert result.status == TruthStatus.UNCERTAIN
    assert result.source_count == 1
    assert result.source_diversity == 1


def test_two_distinct_domains_is_corroborated():
    assert CORROBORATED_MIN_DOMAINS == 2
    result = compute_confidence([_evidence("acme.com"), _evidence("crunchbase.com")], now=NOW)
    assert result.status == TruthStatus.CORROBORATED
    assert result.source_diversity == 2


def test_three_distinct_domains_is_verified():
    assert VERIFIED_MIN_DOMAINS == 3
    result = compute_confidence(
        [_evidence("acme.com"), _evidence("crunchbase.com"), _evidence("techcrunch.com")], now=NOW
    )
    assert result.status == TruthStatus.VERIFIED
    assert result.source_diversity == 3
    assert result.overall_score == 1.0  # full diversity + fresh + all have excerpts


def test_multiple_pages_same_domain_does_not_count_as_diversity():
    result = compute_confidence(
        [_evidence("acme.com"), _evidence("acme.com"), _evidence("acme.com")], now=NOW
    )
    assert result.source_count == 3
    assert result.source_diversity == 1
    assert result.status == TruthStatus.UNCERTAIN


def test_stale_evidence_is_outdated_regardless_of_diversity():
    old = OUTDATED_DAYS + 1
    result = compute_confidence(
        [_evidence("acme.com", age_days=old), _evidence("crunchbase.com", age_days=old)], now=NOW
    )
    assert result.status == TruthStatus.OUTDATED
    assert result.freshness_score == 0.0


def test_one_fresh_source_among_stale_ones_avoids_outdated():
    result = compute_confidence(
        [
            _evidence("acme.com", age_days=OUTDATED_DAYS + 10),
            _evidence("crunchbase.com", age_days=0),
        ],
        now=NOW,
    )
    assert result.status == TruthStatus.CORROBORATED
    assert result.freshness_score == 1.0


def test_evidence_completeness_reflects_missing_excerpts():
    result = compute_confidence(
        [_evidence("acme.com", excerpt="real text"), _evidence("crunchbase.com", excerpt=None)],
        now=NOW,
    )
    assert result.evidence_completeness == 0.5


def test_evidence_completeness_treats_blank_excerpt_as_missing():
    result = compute_confidence([_evidence("acme.com", excerpt="   ")], now=NOW)
    assert result.evidence_completeness == 0.0


def test_freshness_decays_between_grace_period_and_outdated_threshold():
    midpoint_days = OUTDATED_DAYS / 2 + 15  # halfway through the decay window
    result = compute_confidence([_evidence("acme.com", age_days=midpoint_days)], now=NOW)
    assert 0.0 < result.freshness_score < 1.0
