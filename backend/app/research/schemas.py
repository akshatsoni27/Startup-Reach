from datetime import datetime
from enum import StrEnum
from typing import Any
from uuid import UUID

from pydantic import AnyHttpUrl, BaseModel, ConfigDict, Field


class ClaimStatus(StrEnum):
    VERIFIED = "verified"
    INFERENCE = "inference"
    UNKNOWN = "unknown"


class ResearchStatus(StrEnum):
    COMPLETED = "completed"
    PARTIAL = "partial"
    UNAVAILABLE = "unavailable"


class SourceReference(BaseModel):
    model_config = ConfigDict(extra="forbid")

    url: AnyHttpUrl
    title: str | None = None
    evidence_text: str = Field(min_length=1)
    retrieved_at: datetime


class ResearchClaim(BaseModel):
    model_config = ConfigDict(extra="forbid")

    claim: str = Field(min_length=1)
    status: ClaimStatus
    source_urls: list[AnyHttpUrl] = Field(default_factory=list)
    metadata: dict[str, Any] | None = None


class CompanyResearch(BaseModel):
    model_config = ConfigDict(extra="forbid")

    company_id: UUID
    overview: ResearchClaim | None = None
    products_and_services: list[ResearchClaim] = Field(default_factory=list)
    technical_context: list[ResearchClaim] = Field(default_factory=list)
    activity_signals: list[ResearchClaim] = Field(default_factory=list)
    sources: list[SourceReference] = Field(default_factory=list)
    status: ResearchStatus
    errors: list[str] = Field(default_factory=list)
