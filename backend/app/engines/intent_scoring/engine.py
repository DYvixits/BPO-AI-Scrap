"""Intent Scoring Engine (AUDIT_BPO_CRM.md Phase 8): aggregates a
Company's Commercial Signals (Phase 7) into one intent score — "how much
buying-relevant activity is happening at this company right now."

`score` is the mean of `decayed_strength` across all of a company's
`CommercialSignal` rows — unweighted by polarity. Both a funding round
and a round of layoffs mean something is *changing* at the company, and
change is what a BPO sales team wants surfaced; deciding that funding is
"better" than layoffs for a given tenant's pitch is a per-tenant judgment
call this phase doesn't make (same reasoning `commercial_signals/
detector.py` gives for its own uniform `base_weight`). `contributing_
signals` carries each signal's `polarity` through unchanged so a caller
— a human reading "Why This Lead," or a later phase — can still weigh it
themselves.

`score` is `0.0`, not `None`, when a company has zero detected signals:
"we found nothing happening" is itself a real, computed answer, unlike
Fit Scoring's "we had nothing to check against."
"""

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class SignalInput:
    signal_type: str
    polarity: str
    decayed_strength: float


@dataclass(frozen=True, slots=True)
class IntentResult:
    score: float
    contributing_signals: list[dict]


def compute_intent(signals: list[SignalInput]) -> IntentResult:
    if not signals:
        return IntentResult(score=0.0, contributing_signals=[])
    average = sum(s.decayed_strength for s in signals) / len(signals)
    contributing = [
        {
            "signal_type": s.signal_type,
            "polarity": s.polarity,
            "decayed_strength": s.decayed_strength,
        }
        for s in signals
    ]
    return IntentResult(score=round(average, 2), contributing_signals=contributing)
