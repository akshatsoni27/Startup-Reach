from uuid import UUID

from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from app.contacts.schemas import ContactVerificationStatus
from app.drafting.schemas import (
    DraftBody,
    DraftRequest,
    DraftResponse,
    DraftStatus,
    DraftSubject,
    PersonalizationEvidence,
)
from app.models import Company, Contact, EmailDraft, UserProfile
from app.research.schemas import ClaimStatus, CompanyResearch
from app.scoring.schemas import OpportunityScore


class EmailDraftingService:
    """Creates and edits manual email drafts from evidence-backed context."""

    def __init__(self, session: Session | None = None) -> None:
        self._session = session

    def generate(
        self,
        profile: UserProfile,
        company: Company,
        *,
        contact: Contact | None = None,
        research: CompanyResearch | None = None,
        opportunity_score: OpportunityScore | None = None,
        draft_request: DraftRequest | None = None,
    ) -> DraftResponse:
        if draft_request is not None and draft_request.company_id != company.id:
            raise ValueError("draft request company does not match the supplied company")
        recipient = self._verified_contact(contact)
        evidence = self._evidence(company, research)
        subject = self._subject(company)
        body = self._body(profile, company, recipient, evidence)
        response = DraftResponse(
            company_id=company.id,
            contact_id=recipient.id if recipient else None,
            subject=DraftSubject(text=subject),
            body=DraftBody(text=body),
            recipient_name=recipient.name if recipient else None,
            recipient_role=recipient.role if recipient else None,
            personalization_evidence=evidence,
            status=DraftStatus.DRAFT,
            manual_only=True,
            metadata={
                "opportunity_score": opportunity_score.score
                if opportunity_score
                else company.opportunity_score,
                "confirmed_vacancy": False,
            },
        )
        if self._session is not None:
            return self._persist(response)
        return response

    def edit(
        self,
        draft_id: UUID,
        *,
        subject: str | None = None,
        body: str | None = None,
        status: DraftStatus | None = None,
    ) -> DraftResponse:
        draft = self._require_draft(draft_id)
        if subject is not None:
            draft.subject = DraftSubject(text=subject).text
        if body is not None:
            draft.body = DraftBody(text=body).text
        if status is not None:
            draft.status = status.value
        self._session.commit()
        return self._to_response(draft)

    def regenerate(
        self,
        draft_id: UUID,
        profile: UserProfile,
        company: Company,
        *,
        contact: Contact | None = None,
        research: CompanyResearch | None = None,
        opportunity_score: OpportunityScore | None = None,
    ) -> DraftResponse:
        draft = self._require_draft(draft_id)
        regenerated = EmailDraftingService().generate(
            profile,
            company,
            contact=contact,
            research=research,
            opportunity_score=opportunity_score,
        )
        draft.subject = regenerated.subject.text
        draft.body = regenerated.body.text
        draft.personalization_evidence = [
            item.model_dump(mode="json") for item in regenerated.personalization_evidence
        ]
        draft.status = DraftStatus.DRAFT.value
        self._session.commit()
        return self._to_response(draft)

    def _persist(self, response: DraftResponse) -> DraftResponse:
        try:
            draft = EmailDraft(
                company_id=response.company_id,
                contact_id=response.contact_id,
                subject=response.subject.text,
                body=response.body.text,
                personalization_evidence=[
                    item.model_dump(mode="json")
                    for item in response.personalization_evidence
                ],
                status=response.status.value,
            )
            self._session.add(draft)
            self._session.commit()
            return response.model_copy(update={"id": draft.id})
        except SQLAlchemyError as exc:
            self._session.rollback()
            raise RuntimeError("Database error while persisting email draft.") from exc

    def _require_draft(self, draft_id: UUID) -> EmailDraft:
        if self._session is None:
            raise RuntimeError("A database session is required for draft editing.")
        draft = self._session.get(EmailDraft, draft_id)
        if draft is None:
            raise ValueError("Email draft was not found.")
        return draft

    @staticmethod
    def _verified_contact(contact: Contact | None) -> Contact | None:
        if contact is None:
            return None
        if contact.email_verification_status not in {
            ContactVerificationStatus.VERIFIED_OFFICIAL_SOURCE.value,
            ContactVerificationStatus.SUPPORTED_PUBLIC_SOURCE.value,
        }:
            return None
        return contact

    @staticmethod
    def _subject(company: Company) -> str:
        return f"Exploring potential engineering opportunities at {company.name}"

    @staticmethod
    def _body(
        profile: UserProfile,
        company: Company,
        contact: Contact | None,
        evidence: list[PersonalizationEvidence],
    ) -> str:
        greeting = f"Hi {contact.name}," if contact else "Hello,"
        skills = _natural_list(profile.skills[:3])
        introduction = (
            f"My name is {profile.name}, and I work with {skills}."
            if profile.name and skills
            else "My name is a software engineer interested in building useful products."
        )
        observation = (
            f"I was interested to learn that {evidence[0].claim}"
            if evidence
            else f"I came across {company.name} while researching companies building products in this space."
        )
        contribution = (
            f"My background includes {skills}, and I would be glad to explore where that experience could be useful."
            if skills
            else "I would be glad to explore where my software engineering experience could be useful."
        )
        return (
            f"{greeting}\n\n"
            f"{introduction}\n\n"
            f"{observation} {contribution}\n\n"
            "I would be grateful to learn whether there might be a potential engineering "
            "opportunity to discuss, even if there is no advertised vacancy. "
            "Would you be open to a brief conversation?\n\n"
            f"Best,\n{profile.name or 'A software engineer'}"
        )

    @staticmethod
    def _evidence(
        company: Company, research: CompanyResearch | None
    ) -> list[PersonalizationEvidence]:
        evidence: list[PersonalizationEvidence] = []
        if research:
            claims = [
                research.overview,
                *research.products_and_services,
                *research.technical_context,
            ]
            for claim in claims:
                if claim and claim.status == ClaimStatus.VERIFIED and claim.source_urls:
                    evidence.append(
                        PersonalizationEvidence(
                            claim=claim.claim,
                            source_url=str(claim.source_urls[0]),
                        )
                    )
        if not evidence and company.description and company.sources:
            source = company.sources[0]
            evidence.append(
                PersonalizationEvidence(
                    claim=company.description,
                    source_url=source.source_url,
                )
            )
        return evidence

    def _to_response(self, draft: EmailDraft) -> DraftResponse:
        contact = draft.contact
        return DraftResponse(
            id=draft.id,
            company_id=draft.company_id,
            contact_id=draft.contact_id,
            subject=DraftSubject(text=draft.subject),
            body=DraftBody(text=draft.body),
            recipient_name=contact.name if contact else None,
            recipient_role=contact.role if contact else None,
            personalization_evidence=[
                PersonalizationEvidence.model_validate(item)
                for item in draft.personalization_evidence
            ],
            status=DraftStatus(draft.status),
            manual_only=True,
            metadata={"confirmed_vacancy": False},
        )


def _natural_list(values: list[str]) -> str:
    if not values:
        return ""
    if len(values) == 1:
        return values[0]
    return f"{', '.join(values[:-1])}, and {values[-1]}"
