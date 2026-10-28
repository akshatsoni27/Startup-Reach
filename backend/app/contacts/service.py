from datetime import datetime, timezone
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from app.contacts.providers import ContactResearchProvider
from app.contacts.schemas import (
    ContactChannelType,
    ContactResearch,
    ContactResearchResult,
    ContactVerificationStatus,
)
from app.models import Company, Contact, ContactSource


class ContactResearchService:
    """Persists only identity and channel claims backed by public sources."""

    def __init__(self, session: Session, provider: ContactResearchProvider) -> None:
        self._session = session
        self._provider = provider

    def research(self, company: Company) -> ContactResearchResult:
        try:
            result = self._provider.research_contacts(company)
        except RuntimeError as exc:
            result = ContactResearchResult(
                company_id=company.id,
                status="unavailable",
                errors=[str(exc)],
            )

        try:
            persisted = self._persist(company, result)
        except SQLAlchemyError as exc:
            self._session.rollback()
            raise RuntimeError("Database error while persisting contact research.") from exc
        return result.model_copy(update={"contacts": persisted})

    def _persist(
        self, company: Company, result: ContactResearchResult
    ) -> list[ContactResearch]:
        persisted: list[ContactResearch] = []
        for research in result.contacts:
            if not self._is_supported(research):
                continue
            contact = self._find_existing(company.id, research)
            if contact is None:
                contact = Contact(
                    company=company,
                    name=research.name,
                    role=research.role,
                    email_verification_status=research.verification_status.value,
                    confidence_score=research.confidence_score,
                    research_status="researched",
                )
                self._session.add(contact)
                self._session.flush()
            else:
                self._merge_contact(contact, research)

            for source in research.sources:
                self._add_source_if_new(contact, source.url, source.evidence_text)
            self._merge_channels(contact, research)
            persisted.append(research)
        self._session.commit()
        return persisted

    @staticmethod
    def _is_supported(research: ContactResearch) -> bool:
        return (
            research.verification_status
            in {
                ContactVerificationStatus.VERIFIED_OFFICIAL_SOURCE,
                ContactVerificationStatus.SUPPORTED_PUBLIC_SOURCE,
            }
            and bool(research.sources)
        )

    def _find_existing(self, company_id: UUID, research: ContactResearch) -> Contact | None:
        candidates = self._session.scalars(
            select(Contact).where(Contact.company_id == company_id)
        ).all()
        profile_urls = {
            channel.value
            for channel in research.channels
            if channel.channel_type == ContactChannelType.PROFESSIONAL_PROFILE
        }
        emails = {
            channel.value.lower()
            for channel in research.channels
            if channel.channel_type == ContactChannelType.PUBLIC_EMAIL
        }
        for contact in candidates:
            if contact.professional_profile_url in profile_urls:
                return contact
            if contact.email and contact.email.lower() in emails:
                return contact
            if contact.name.casefold() == research.name.casefold():
                return contact
        return None

    @staticmethod
    def _merge_contact(contact: Contact, research: ContactResearch) -> None:
        if research.confidence_score > (contact.confidence_score or 0):
            contact.confidence_score = research.confidence_score
            contact.email_verification_status = research.verification_status.value
        if not contact.role:
            contact.role = research.role
        contact.research_status = "researched"

    def _merge_channels(self, contact: Contact, research: ContactResearch) -> None:
        for channel in research.channels:
            if channel.channel_type == ContactChannelType.PUBLIC_EMAIL:
                if contact.email is None:
                    contact.email = channel.value
            elif channel.channel_type == ContactChannelType.PROFESSIONAL_PROFILE:
                if contact.professional_profile_url is None:
                    contact.professional_profile_url = channel.value
            elif channel.channel_type == ContactChannelType.COMPANY_CONTACT:
                if contact.company_contact_url is None:
                    contact.company_contact_url = channel.value
            for source_url in channel.source_urls:
                self._add_source_if_new(contact, source_url, f"Public channel: {channel.value}")

    @staticmethod
    def _add_source_if_new(contact: Contact, url, evidence_text: str) -> None:
        if any(source.source_url == str(url) for source in contact.sources):
            return
        contact.sources.append(
            ContactSource(
                source_url=str(url),
                evidence_text=evidence_text,
                retrieved_at=datetime.now(timezone.utc),
            )
        )
