from app.engines.intent_scoring.engine import SignalInput, compute_intent


def test_no_signals_returns_zero_not_none():
    result = compute_intent([])
    assert result.score == 0.0
    assert result.contributing_signals == []


def test_single_signal_score_equals_its_strength():
    result = compute_intent([SignalInput("funding", "positive", 0.8)])
    assert result.score == 0.8
    assert result.contributing_signals == [
        {"signal_type": "funding", "polarity": "positive", "decayed_strength": 0.8}
    ]


def test_score_is_the_average_across_signals():
    signals = [
        SignalInput("funding", "positive", 1.0),
        SignalInput("layoffs", "negative", 0.0),
    ]
    result = compute_intent(signals)
    assert result.score == 0.5


def test_negative_polarity_signals_still_contribute_to_score():
    # Intent is about "is something happening," not "is it good news" —
    # a layoffs signal counts toward the score exactly like a funding one.
    result = compute_intent([SignalInput("layoffs", "negative", 1.0)])
    assert result.score == 1.0
    assert result.contributing_signals[0]["polarity"] == "negative"
