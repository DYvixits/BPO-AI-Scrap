"""Opportunity Scoring Engine (AUDIT_BPO_CRM.md Phase 8): combines Fit,
Intent, Confidence, freshness, and momentum into one score — master spec
§4's `OPPORTUNITY = f(FIT, INTENT, CONFIDENCE, FRESHNESS, MOMENTUM)`.

`f` is meant to be per-tenant-configurable (master spec §56's
Configuration Engine) — that engine doesn't exist in this codebase yet,
so `f` here is one fixed, disclosed weighted average (`DEFAULT_WEIGHTS`
below), not a per-tenant setting; every score row stores the
`weights_used` that actually produced it, so a future Configuration
Engine slots in without changing this function's shape. Every component
that went into the score is also stored on the row, so "Why This Lead"
(master spec §23/§45) is a join over real columns, not a black box, even
before the weights themselves are customizable.

`fit` is treated as a neutral `0.5` when `FitResult.score` is `None`
(nothing to check fit against) rather than dropped from the formula —
dropping it would silently reweight the other four dimensions in a way
nobody asked for; a disclosed neutral default is more honest about
"we don't know" than either extreme.

`momentum` here is a same-snapshot proxy — the fraction of a company's
signals that are `positive` polarity — not a real trend/velocity metric.
A genuine momentum measure needs multiple observations of the same
company over time (e.g. "3 signals last month vs. 1 this month"), and
`companies`/`commercial_signals` are scoped per `research_job`, not
tracked across repeated jobs on the same company (see Phase 5's
REMAINING notes) — that's Phase 10 Monitoring's job, not this phase's.
AUDIT_BPO_CRM.md's Temporal Intelligence Engine row is marked PARTIAL,
not done, for exactly this reason.
"""

from dataclasses import dataclass

from app.engines.intent_scoring.engine import SignalInput

DEFAULT_WEIGHTS: dict[str, float] = {
    "fit": 0.3,
    "intent": 0.3,
    "confidence": 0.2,
    "freshness": 0.1,
    "momentum": 0.1,
}
_NEUTRAL_FIT = 0.5


@dataclass(frozen=True, slots=True)
class OpportunityResult:
    score: float
    fit_component: float
    intent_component: float
    confidence_component: float
    freshness_component: float
    momentum_component: float
    weights_used: dict[str, float]


def compute_momentum(signals: list[SignalInput]) -> float:
    if not signals:
        return 0.0
    positive = sum(1 for s in signals if s.polarity == "positive")
    return round(positive / len(signals), 2)


def compute_opportunity(
    *,
    fit_score: float | None,
    intent_score: float,
    confidence_score: float,
    freshness_score: float,
    momentum: float,
    weights: dict[str, float] | None = None,
) -> OpportunityResult:
    weights_used = dict(weights) if weights is not None else dict(DEFAULT_WEIGHTS)
    fit_component = fit_score if fit_score is not None else _NEUTRAL_FIT

    score = (
        weights_used["fit"] * fit_component
        + weights_used["intent"] * intent_score
        + weights_used["confidence"] * confidence_score
        + weights_used["freshness"] * freshness_score
        + weights_used["momentum"] * momentum
    )

    return OpportunityResult(
        score=round(score, 2),
        fit_component=round(fit_component, 2),
        intent_component=round(intent_score, 2),
        confidence_component=round(confidence_score, 2),
        freshness_component=round(freshness_score, 2),
        momentum_component=round(momentum, 2),
        weights_used=weights_used,
    )
