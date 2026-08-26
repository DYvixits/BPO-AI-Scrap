from uuid import UUID

from pydantic import BaseModel, ConfigDict

from app.schemas.commercial_signal import CommercialSignalOut
from app.schemas.scoring import FitScoreOut, IntentScoreOut, OpportunityScoreOut
from app.schemas.verification import ConfidenceScoreOut, EvidenceOut


class EntityAliasOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    alias_type: str
    value: str
    source_url: str


class CompanyOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    canonical_name: str
    primary_domain: str
    description: str | None
    match_confidence: float
    aliases: list[EntityAliasOut] = []
    # engines/verification (AUDIT_BPO_CRM.md Phase 6) — None until the
    # Verification Engine has run, same lifecycle as aliases above.
    confidence_score: ConfidenceScoreOut | None = None
    evidence: list[EvidenceOut] = []
    # engines/commercial_signals (AUDIT_BPO_CRM.md Phase 7) — same
    # populated-once-after-resolution lifecycle as the fields above.
    signals: list[CommercialSignalOut] = []
    # engines/{fit,intent,opportunity}_scoring (AUDIT_BPO_CRM.md Phase 8)
    # — same populated-once-after-resolution lifecycle as the fields above.
    fit_score: FitScoreOut | None = None
    intent_score: IntentScoreOut | None = None
    opportunity_score: OpportunityScoreOut | None = None
