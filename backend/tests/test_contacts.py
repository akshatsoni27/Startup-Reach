from datetime import datetime, timezone
from uuid import uuid4

import pytest
from sqlalchemy import create_engine, event, select
from sqlalchemy.orm import Session

from app.contacts.schemas import (
    ContactCategory,
    ContactChannel,
    ContactChannelType,
    ContactResearch,
    ContactResearchResult,
    ContactSourceReference,
    ContactVerificationStatus,
)
from app.contacts.service import ContactResearchService
from app.models import Base, Company, Contact, ContactSource


@pytest.fixture()
def session() -> Session:
    engine = create_engine("sqlite:///:memory:")

    @event.listens_for(engine, "connect")
    def enable_foreign_keys(dbapi_connection, _connection_record) -> None:
        dbapi_connection.execute("PRAGMA foreign_keys=ON")

    Base.metadata.create_all(engine)
    with Session(engine) as db:
        yield db
    Base.metadata.drop_all(engine)


def company_record() -> Company:
    return Company(
        id=uuid4(),
        name="Acme",
        website_url="https://acme.example",
        canonical_domain="acme.example",
        technology_focus=[],
    )


def source(url: str = "https://acme.example/team") -> ContactSourceReference:
    return ContactSourceReference(
        url=url,
        title="Team page",
        evidence_text="Alex is CTO at Acme.",
        retrieved_at=datetime.now(timezone.utc),
    )


class FakeProvider:
    name = "mock_public_source"

    def __init__(self, result: ContactResearchResult) -> None:
        self.result = result

    def research_contacts(self, company: Company) -> ContactResearchResult:
        return self.result


def contact_research(
    company_id, *, status=ContactVerificationStatus.SUPPORTED_PUBLIC_SOURCE
) -> ContactResearch:
    return ContactResearch(
        company_id=company_id,
        name="Alex Chen",
        role="CTO",
        category=ContactCategory.CTO,
        channels=[
            ContactChannel(
                channel_type=ContactChannelType.PROFESSIONAL_PROFILE,
                value="https://professional.example/alex",
                source_urls=["https://acme.example/team"],
            )
        ],
        sources=[source()],
        verification_status=status,
        confidence_score=90,
    )


def test_contact_schemas_require_evidence_and_bound_confidence() -> None:
    record = company_record()
    contact = contact_research(record.id)
    assert contact.category == ContactCategory.CTO
    assert contact.verification_status == ContactVerificationStatus.SUPPORTED_PUBLIC_SOURCE
    with pytest.raises(ValueError):
        ContactResearch.model_validate(
            {**contact_research(record.id).model_dump(), "confidence_score": 101}
        )


def test_service_persists_identity_channels_and_sources(session: Session) -> None:
    company = company_record()
    session.add(company)
    session.commit()
    research = contact_research(company.id)

    result = ContactResearchService(
        session,
        FakeProvider(ContactResearchResult(company_id=company.id, contacts=[research], status="completed")),
    ).research(company)

    contact = session.scalar(select(Contact))
    contact_source = session.scalar(select(ContactSource))
    assert len(result.contacts) == 1
    assert contact is not None
    assert contact.name == "Alex Chen"
    assert contact.role == "CTO"
    assert contact.professional_profile_url == "https://professional.example/alex"
    assert contact.email is None
    assert contact.email_verification_status == "supported_by_public_source"
    assert contact.confidence_score == 90
    assert contact_source is not None
    assert contact_source.source_url == "https://acme.example/team"


def test_service_never_persists_unsupported_or_unverified_identity(session: Session) -> None:
    company = company_record()
    session.add(company)
    session.commit()
    unsupported = contact_research(
        company.id, status=ContactVerificationStatus.UNVERIFIED
    )
    result = ContactResearchService(
        session,
        FakeProvider(ContactResearchResult(company_id=company.id, contacts=[unsupported], status="partial")),
    ).research(company)

    assert result.contacts == []
    assert session.scalar(select(Contact)) is None
    assert session.scalar(select(ContactSource)) is None


def test_public_email_is_stored_only_as_provider_supplied_channel(session: Session) -> None:
    company = company_record()
    session.add(company)
    session.commit()
    research = contact_research(company.id)
    research = research.model_copy(
        update={
            "channels": [
                ContactChannel(
                    channel_type=ContactChannelType.PUBLIC_EMAIL,
                    value="alex@acme.example",
                    source_urls=["https://acme.example/contact"],
                )
            ]
        }
    )
    ContactResearchService(
        session,
        FakeProvider(ContactResearchResult(company_id=company.id, contacts=[research], status="completed")),
    ).research(company)

    contact = session.scalar(select(Contact))
    assert contact is not None
    assert contact.email == "alex@acme.example"
    assert contact.professional_profile_url is None
    assert len(session.scalars(select(ContactSource)).all()) == 2


def test_repeated_research_reuses_contact_and_sources(session: Session) -> None:
    company = company_record()
    session.add(company)
    session.commit()
    research = contact_research(company.id)
    provider = FakeProvider(
        ContactResearchResult(company_id=company.id, contacts=[research], status="completed")
    )
    service = ContactResearchService(session, provider)
    service.research(company)
    service.research(company)

    assert len(session.scalars(select(Contact)).all()) == 1
    assert len(session.scalars(select(ContactSource)).all()) == 1
