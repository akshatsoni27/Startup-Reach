from datetime import datetime, timezone
from uuid import uuid4

import pytest
from sqlalchemy import create_engine, event, select
from sqlalchemy.orm import Session

from app.contacts.schemas import ContactVerificationStatus
from app.drafting.schemas import DraftStatus
from app.drafting.service import EmailDraftingService
from app.models import Base, Company, CompanySource, Contact, EmailDraft, UserProfile
from app.research.schemas import ClaimStatus, CompanyResearch, ResearchClaim, ResearchStatus
from app.scoring.schemas import OpportunityScore


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


def profile(**kwargs) -> UserProfile:
    values = {
        "id": uuid4(),
        "name": "Aksha",
        "email": f"{uuid4()}@example.com",
        "skills": ["Python", "FastAPI", "AI agents"],
        "experience": [],
        "projects": [{"name": "An AI application"}],
        "preferred_roles": ["backend engineer"],
        "preferred_locations": [],
        "preferred_industries": [],
    }
    values.update(kwargs)
    return UserProfile(**values)


def company_record() -> Company:
    return Company(
        id=uuid4(),
        name="Acme AI",
        canonical_domain="acme.example",
        website_url="https://acme.example",
        description="Acme builds workflow automation software.",
        technology_focus=["Python"],
    )


def verified_contact(company: Company) -> Contact:
    return Contact(
        id=uuid4(),
        company=company,
        name="Alex Chen",
        role="CTO",
        email_verification_status=ContactVerificationStatus.SUPPORTED_PUBLIC_SOURCE.value,
        professional_profile_url="https://professional.example/alex",
        confidence_score=90,
    )


def test_draft_generation_uses_only_sourced_personalization() -> None:
    company = company_record()
    company.sources = [
        CompanySource(
            source_url="https://acme.example/about",
            source_type="official_website",
            evidence_text="Acme builds workflow automation software.",
        )
    ]
    research = CompanyResearch(
        company_id=company.id,
        products_and_services=[
            ResearchClaim(
                claim="Acme builds workflow automation software.",
                status=ClaimStatus.VERIFIED,
                source_urls=["https://acme.example/about"],
            )
        ],
        status=ResearchStatus.COMPLETED,
    )

    draft = EmailDraftingService().generate(
        profile(),
        company,
        contact=verified_contact(company),
        research=research,
        opportunity_score=None,
    )

    assert draft.subject.text.startswith("Exploring potential engineering")
    assert "Hi Alex Chen," in draft.body.text
    assert "workflow automation software" in draft.body.text
    assert draft.personalization_evidence[0].source_url == "https://acme.example/about"
    assert "advertised vacancy" in draft.body.text
    assert draft.manual_only is True
    assert draft.metadata == {"opportunity_score": None, "confirmed_vacancy": False}


def test_missing_context_uses_neutral_language() -> None:
    company = company_record()
    company.description = None
    company.sources = []
    draft = EmailDraftingService().generate(profile(skills=[]), company)

    assert draft.recipient_name is None
    assert draft.personalization_evidence == []
    assert "came across Acme AI" in draft.body.text
    assert "invent" not in draft.body.text.lower()


def test_unverified_contact_is_not_used_as_recipient() -> None:
    company = company_record()
    contact = Contact(
        name="Unverified Person",
        role="Founder",
        email_verification_status=ContactVerificationStatus.UNVERIFIED.value,
    )

    draft = EmailDraftingService().generate(profile(), company, contact=contact)

    assert draft.recipient_name is None
    assert draft.contact_id is None
    assert "Hi Unverified Person" not in draft.body.text


def test_draft_persistence_editing_and_regeneration(session: Session) -> None:
    company = company_record()
    contact = verified_contact(company)
    session.add(company)
    session.commit()
    service = EmailDraftingService(session)

    created = service.generate(profile(), company, contact=contact)
    persisted = session.get(EmailDraft, created.id)
    assert persisted is not None
    assert persisted.status == "draft"

    edited = service.edit(created.id, subject="Edited subject", body="Edited body", status=DraftStatus.READY_TO_SEND)
    assert edited.subject.text == "Edited subject"
    assert edited.status == DraftStatus.READY_TO_SEND

    regenerated = service.regenerate(created.id, profile(skills=["Django"]), company, contact=contact)
    assert regenerated.status == DraftStatus.DRAFT
    assert "Django" in regenerated.body.text
    assert regenerated.body.text != "Edited body"


def test_draft_can_include_opportunity_score_without_claiming_hiring() -> None:
    company = company_record()
    score = OpportunityScore.model_validate(
        {
            "company_id": company.id,
            "score": 80,
            "label": "High potential match",
            "opportunity_status": "potential_opportunity",
            "breakdown": {
                "factors": [],
                "weights_total": 0,
                "explanation": "Potential only",
                "missing_information": [],
            },
            "metadata": {"confirmed_vacancy": False},
        }
    )
    draft = EmailDraftingService().generate(profile(), company, opportunity_score=score)
    assert draft.metadata["opportunity_score"] == 80
    assert draft.metadata["confirmed_vacancy"] is False
    assert "hiring" not in draft.body.text.lower()
    assert not hasattr(EmailDraftingService, "send")
