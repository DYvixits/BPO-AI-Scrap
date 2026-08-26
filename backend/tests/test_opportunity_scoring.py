from app.engines.intent_scoring.engine import SignalInput
from app.engines.opportunity_scoring.engine import (
    DEFAULT_WEIGHTS,
    compute_momentum,
    compute_opportunity,
)


def test_default_weights_sum_to_one():
    assert round(sum(DEFAULT_WEIGHTS.values()), 6) == 1.0


def test_all_zero_inputs_score_zero():
    result = compute_opportunity(
        fit_score=0.0, intent_score=0.0, confidence_score=0.0, freshness_score=0.0, momentum=0.0
    )
    assert result.score == 0.0


def test_all_max_inputs_score_one():
    result = compute_opportunity(
        fit_score=1.0, intent_score=1.0, confidence_score=1.0, freshness_score=1.0, momentum=1.0
    )
    assert result.score == 1.0


def test_none_fit_score_uses_neutral_default():
    with_none = compute_opportunity(
        fit_score=None, intent_score=0.0, confidence_score=0.0, freshness_score=0.0, momentum=0.0
    )
    with_half = compute_opportunity(
        fit_score=0.5, intent_score=0.0, confidence_score=0.0, freshness_score=0.0, momentum=0.0
    )
    assert with_none.score == with_half.score
    assert with_none.fit_component == 0.5


def test_weights_used_is_recorded_on_the_result():
    result = compute_opportunity(
        fit_score=0.5, intent_score=0.5, confidence_score=0.5, freshness_score=0.5, momentum=0.5
    )
    assert result.weights_used == DEFAULT_WEIGHTS


def test_custom_weights_are_respected():
    custom = {"fit": 1.0, "intent": 0.0, "confidence": 0.0, "freshness": 0.0, "momentum": 0.0}
    result = compute_opportunity(
        fit_score=0.8,
        intent_score=1.0,
        confidence_score=1.0,
        freshness_score=1.0,
        momentum=1.0,
        weights=custom,
    )
    assert result.score == 0.8


def test_momentum_is_zero_with_no_signals():
    assert compute_momentum([]) == 0.0


def test_momentum_is_fraction_of_positive_signals():
    signals = [
        SignalInput("funding", "positive", 1.0),
        SignalInput("hiring", "positive", 1.0),
        SignalInput("layoffs", "negative", 1.0),
    ]
    assert compute_momentum(signals) == round(2 / 3, 2)


def test_momentum_is_one_when_all_signals_positive():
    signals = [SignalInput("funding", "positive", 1.0)]
    assert compute_momentum(signals) == 1.0
