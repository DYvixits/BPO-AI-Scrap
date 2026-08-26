from pydantic import BaseModel, ConfigDict


class EvidenceOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    source_url: str
    domain: str
    excerpt: str | None


class ConfidenceScoreOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    status: str
    source_count: int
    source_diversity: int
    freshness_score: float
    evidence_completeness: float
    overall_score: float
