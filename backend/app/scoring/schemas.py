from typing import Any
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, model_validator


class EvidenceReference(BaseModel):
    model_config = ConfigDict(extra="forbid")

    source_url: str
    evidence: str = Field(min_length=1)


class ScoringFactor(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str
    score: float = Field(ge=0, le=100)
    weight: float = Field(gt=0)
    weighted_score: float = Field(ge=0)
    explanation: str
    evidence: list[EvidenceReference] = Field(default_factory=list)
    missing_information: list[str] = Field(default_factory=list)


class ScoreBreakdown(BaseModel):
    model_config = ConfigDict(extra="forbid")

    factors: list[ScoringFactor]
    weights_total: float
    explanation: str
    missing_information: list[str] = Field(default_factory=list)

    @model_validator(mode="after")
    def validate_weights(self) -> "ScoreBreakdown":
        if abs(sum(factor.weight for factor in self.factors) - self.weights_total) > 0.001:
            raise ValueError("factor weights must equal weights_total")
        return self


class OpportunityScore(BaseModel):
    model_config = ConfigDict(extra="forbid")

    company_id: UUID
    score: int = Field(ge=0, le=100)
    label: str
    opportunity_status: str
    breakdown: ScoreBreakdown
    metadata: dict[str, Any] | None = None
