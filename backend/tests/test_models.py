from uuid import uuid4

import pytest
from sqlalchemy import create_engine, event
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.models import Base, Company, CompanySource, Contact, EmailDraft


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


def test_company_relationships_and_cascades(session: Session) -> None:
    company = Company(
        name="Example AI",
        canonical_domain="example.ai",
        technology_focus=["AI", "Python"],
    )
    contact = Contact(name="Founder", role="Founder", company=company)
    source = CompanySource(
        source_type="official_website",
        source_url="https://example.ai/about",
        company=company,
    )
    session.add(company)
    session.commit()

    assert contact.company is company
    assert source.company is company
    assert company.contacts == [contact]
    assert company.sources == [source]

    session.delete(company)
    session.commit()
    assert session.get(Contact, contact.id) is None
    assert session.get(CompanySource, source.id) is None


def test_unique_company_domain_is_enforced(session: Session) -> None:
    session.add_all(
        [
            Company(name="One", canonical_domain="same.example"),
            Company(name="Two", canonical_domain="same.example"),
        ]
    )

    with pytest.raises(IntegrityError):
        session.commit()


def test_email_draft_references_company_and_is_not_a_sender(session: Session) -> None:
    company = Company(name="Draftable", technology_focus=[])
    draft = EmailDraft(
        company=company,
        subject="Exploring a potential opportunity",
        body="Hello there",
        personalization_evidence=["Official product page"],
    )
    session.add(draft)
    session.commit()

    assert draft.status == "draft"
    assert draft.company_id == company.id
    assert not hasattr(draft, "send")


def test_score_and_draft_status_constraints_are_enforced(session: Session) -> None:
    invalid_company = Company(
        name="Invalid score",
        technology_focus=[],
        opportunity_score=101,
    )
    session.add(invalid_company)
    with pytest.raises(IntegrityError):
        session.commit()

    session.rollback()
    company = Company(name="Invalid draft", technology_focus=[])
    session.add(company)
    session.flush()
    invalid_draft = EmailDraft(
        company_id=company.id,
        subject="Subject",
        body="Body",
        personalization_evidence=[],
        status="sent",
    )
    session.add(invalid_draft)
    with pytest.raises(IntegrityError):
        session.commit()


def test_uuid_primary_keys_are_generated(session: Session) -> None:
    company = Company(name="UUID startup", technology_focus=[])
    session.add(company)
    session.commit()

    assert company.id is not None
    assert company.id != uuid4()
