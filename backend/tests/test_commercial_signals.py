from datetime import UTC, datetime, timedelta

from app.engines.commercial_signals.detector import (
    SIGNAL_DECAY_DAYS,
    CommercialSignalType,
    decay_strength,
    detect_signals,
)
from app.engines.query_intelligence.keywords import SIGNALS

NOW = datetime(2026, 1, 1, tzinfo=UTC)


def test_signal_type_enum_stays_in_sync_with_query_intelligence_vocabulary():
    assert {member.value for member in CommercialSignalType} == set(SIGNALS.keys())


def test_no_text_returns_no_signals():
    assert detect_signals(None) == []
    assert detect_signals("") == []


def test_detects_funding_signal():
    text = "Acme announced today that it raised $10M in a Series A round."
    detected = detect_signals(text)
    types = {d.signal_type for d in detected}
    assert CommercialSignalType.FUNDING in types


def test_detects_multiple_distinct_signal_types_on_one_page():
    text = "Acme is hiring across the board after raising a new funding round."
    detected = detect_signals(text)
    types = {d.signal_type for d in detected}
    assert CommercialSignalType.HIRING in types
    assert CommercialSignalType.FUNDING in types


def test_matching_is_case_insensitive():
    text = "ACME IS HIRING NOW — apply today."
    detected = detect_signals(text)
    assert any(d.signal_type == CommercialSignalType.HIRING for d in detected)


def test_at_most_one_signal_per_type_per_call():
    text = "We are hiring. We are also hiring more people. Join our recruiting team."
    detected = [d for d in detect_signals(text) if d.signal_type == CommercialSignalType.HIRING]
    assert len(detected) == 1


def test_excerpt_is_bounded_and_contains_the_keyword():
    text = "x" * 500 + " hiring " + "y" * 500
    detected = detect_signals(text)
    hiring = next(d for d in detected if d.signal_type == CommercialSignalType.HIRING)
    assert "hiring" in hiring.excerpt
    assert len(hiring.excerpt) < len(text)


def test_polarity_is_carried_from_signals_table():
    text = "Acme announced layoffs affecting 10% of staff."
    detected = detect_signals(text)
    layoffs = next(d for d in detected if d.signal_type == CommercialSignalType.LAYOFFS)
    assert layoffs.polarity == "negative"


def test_decay_is_full_strength_at_zero_age():
    assert decay_strength(1.0, crawled_at=NOW, now=NOW) == 1.0


def test_decay_is_zero_past_decay_window():
    old = NOW - timedelta(days=SIGNAL_DECAY_DAYS + 1)
    assert decay_strength(1.0, crawled_at=old, now=NOW) == 0.0


def test_decay_is_linear_at_midpoint():
    midpoint = NOW - timedelta(days=SIGNAL_DECAY_DAYS / 2)
    assert decay_strength(1.0, crawled_at=midpoint, now=NOW) == 0.5


def test_decay_handles_naive_datetimes_without_raising():
    naive_crawled_at = datetime(2026, 1, 1)
    naive_now = datetime(2026, 1, 1)
    assert decay_strength(1.0, crawled_at=naive_crawled_at, now=naive_now) == 1.0
