from pydantic import BaseModel, ConfigDict


class CommercialSignalOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    signal_type: str
    polarity: str
    matched_keyword: str
    excerpt: str
    source_url: str
    base_weight: float
    decayed_strength: float
