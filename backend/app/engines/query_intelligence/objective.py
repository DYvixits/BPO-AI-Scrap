"""ResearchObjective — the structured plan a natural-language research
request gets turned into (master spec §4). Every field below is either
populated by the heuristic parser (parser.py) with the keyword(s) that
matched attached under `matched_keywords`, or left at its default with an
empty match list — nothing here is ever silently invented. There is no LLM
in this phase (that's Phase 9's AI Orchestrator, deliberately sequenced
after Phase 6's Verification Engine gives it something to ground against —
see docs/AUDIT_BPO_CRM.md §6); this is intentionally a transparent,
inspectable rule-based pass, not a black box.
"""

from pydantic import BaseModel, Field


class ResearchObjective(BaseModel):
    target_entities: list[str] = Field(
        default_factory=lambda: ["company"],
        description="Kinds of entity being sought — e.g. company, person.",
    )
    geography: list[str] = Field(
        default_factory=list, description="Countries/regions matched in the query."
    )
    industry: list[str] = Field(
        default_factory=list, description="Industry/sector keywords matched."
    )
    company_size_min: int | None = None
    company_size_max: int | None = None
    required_attributes: list[str] = Field(
        default_factory=list, description="Fields the query explicitly asks for."
    )
    signals: list[str] = Field(
        default_factory=list,
        description="Commercial signal keywords detected (hiring, funding, ...).",
    )
    freshness: str = Field(
        default="any", description='"recent" if the query asks for current/latest info, else "any".'
    )
    matched_keywords: dict[str, list[str]] = Field(
        default_factory=dict,
        description="Which literal words in the query produced each field above — "
        "for explainability ('why did the system think this was about fintech?').",
    )
