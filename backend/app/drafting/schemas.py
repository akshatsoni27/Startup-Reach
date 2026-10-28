from enum import StrEnum
from typing import Any
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


class DraftStatus(StrEnum):
    DRAFT = "draft"
    READY_TO_SEND = "ready_to_send"
    ARCHIVED = "archived"


class DraftSubject(BaseModel):
    model_config = ConfigDict(extra="forbid")

    text: str = Field(min_length=1, max_length=500)


class DraftBody(BaseModel):
    model_config = ConfigDict(extra="forbid")

    text: str = Field(min_length=1)


class PersonalizationEvidence(BaseModel):
    model_config = ConfigDict(extra="forbid")

    claim: str = Field(min_length=1)
    source_url: str | None = None


class DraftRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    company_id: UUID
    contact_id: UUID | None = None
    regenerate_from_draft_id: UUID | None = None


class DraftResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: UUID | None = None
    company_id: UUID
    contact_id: UUID | None = None
    subject: DraftSubject
    body: DraftBody
    recipient_name: str | None = None
    recipient_role: str | None = None
    personalization_evidence: list[PersonalizationEvidence] = Field(default_factory=list)
    status: DraftStatus = DraftStatus.DRAFT
    manual_only: bool = True
    metadata: dict[str, Any] | None = None
