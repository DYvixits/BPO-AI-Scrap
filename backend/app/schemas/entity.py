from uuid import UUID

from pydantic import BaseModel, ConfigDict


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
