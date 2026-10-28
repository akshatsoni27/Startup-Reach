from datetime import datetime
from enum import StrEnum
from typing import Any
from uuid import UUID

from pydantic import AnyHttpUrl, BaseModel, ConfigDict, Field


class ContactCategory(StrEnum):
    FOUNDER = "founder"
    COFOUNDER = "co_founder"
    CTO = "cto"
    TECHNICAL_COFOUNDER = "technical_cofounder"
    ENGINEERING_LEADER = "engineering_leader"


class ContactVerificationStatus(StrEnum):
    VERIFIED_OFFICIAL_SOURCE = "verified_from_official_source"
    SUPPORTED_PUBLIC_SOURCE = "supported_by_public_source"
    UNVERIFIED = "unverified"
    NOT_FOUND = "not_found"


class ContactChannelType(StrEnum):
    PUBLIC_EMAIL = "public_email"
    PROFESSIONAL_PROFILE = "professional_profile"
    COMPANY_CONTACT = "company_contact"


class ContactChannel(BaseModel):
    model_config = ConfigDict(extra="forbid")

    channel_type: ContactChannelType
    value: str = Field(min_length=1)
    source_urls: list[AnyHttpUrl] = Field(default_factory=list)


class ContactSourceReference(BaseModel):
    model_config = ConfigDict(extra="forbid")

    url: AnyHttpUrl
    title: str | None = None
    evidence_text: str = Field(min_length=1)
    retrieved_at: datetime


class ContactResearch(BaseModel):
    model_config = ConfigDict(extra="forbid")

    company_id: UUID
    name: str = Field(min_length=1)
    role: str = Field(min_length=1)
    category: ContactCategory
    channels: list[ContactChannel] = Field(default_factory=list)
    sources: list[ContactSourceReference] = Field(default_factory=list)
    verification_status: ContactVerificationStatus
    confidence_score: int = Field(ge=0, le=100)
    metadata: dict[str, Any] | None = None


class ContactResearchResult(BaseModel):
    model_config = ConfigDict(extra="forbid")

    company_id: UUID
    contacts: list[ContactResearch] = Field(default_factory=list)
    status: str
    errors: list[str] = Field(default_factory=list)
