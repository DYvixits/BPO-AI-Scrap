from datetime import datetime
from typing import Any
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

from app.engines.query_intelligence.objective import ResearchObjective
from app.models.research import ResearchMode, ResearchStatus


class ResearchCreateRequest(BaseModel):
    query: str = Field(
        min_length=3, max_length=2000, description="Natural-language research request"
    )
    mode: ResearchMode = ResearchMode.BALANCED
    config: dict[str, Any] = Field(
        default_factory=dict,
        description="Advanced overrides (max_pages, max_domains, min_sources, ...). "
        "Unset fields fall back to the selected mode's defaults.",
    )


class ResearchJobOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    query: str
    status: ResearchStatus
    mode: ResearchMode
    config: dict[str, Any]
    objective: ResearchObjective
    error: str | None
    created_at: datetime
    started_at: datetime | None
    completed_at: datetime | None


class ResearchEventOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    kind: str
    payload: dict[str, Any]
    created_at: datetime


class ResearchResultOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    title: str | None
    url: str
    snippet: str | None
    confidence: float


class ResearchJobDetailOut(ResearchJobOut):
    events: list[ResearchEventOut] = Field(default_factory=list)
