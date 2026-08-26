from pydantic import BaseModel, ConfigDict


class FitScoreOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    score: float | None
    matched_factors: list[str]
    unmatched_factors: list[str]


class IntentScoreOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    score: float
    contributing_signals: list[dict]


class OpportunityScoreOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    score: float
    fit_component: float
    intent_component: float
    confidence_component: float
    freshness_component: float
    momentum_component: float
    weights_used: dict[str, float]
