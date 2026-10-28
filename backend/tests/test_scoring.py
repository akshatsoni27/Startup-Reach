from datetime import datetime, timezone
from uuid import uuid4

import pytest
from sqlalchemy import create_engine, event
from sqlalchemy.orm import Session

from app.contacts.schemas import ContactVerificationStatus
from app.models import Base, Company, Contact, CompanySource, UserProfile
from app.research.schemas import ClaimStatus, CompanyResearch, ResearchClaim, ResearchStatus
from app.scoring.schemas import ScoreBreakdown
from app.scoring.service import OpportunityScoringService, ScoringWeights


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
        "name": "Developer",
        "email": f"{uuid4()}@example.com",
        "skills": ["Python", "AI", "FastAPI"],
        "experience": [{"summary": "backend software engineering"}],
        "projects": [{"summary": "AI agents with Python"}],
        "preferred_roles": ["engineer", "backend"],
        "preferred_locations": [],
        "preferred_industries": ["AI"],
    }
    values.update(kwargs)
    return UserProfile(**values)


def company(**kwargs) -> Company:
    values = {
        "id": uuid4(),
        "name": "Acme AI",
        "description": "AI software platform for backend teams",
        "technology_focus": ["Python", "AI", "FastAPI"],
        "company_stage": "seed",
        "research_status": "completed",
    }
    values.update(kwargs)
    return Company(**values)


def test_high_relevance_is_explainable_and_potential_not_vacancy(session: Session) -> None:
    record = company()
    record.contacts = [
        Contact(
            name="Founder",
            role="Founder",
            email_verification_status=ContactVerificationStatus.SUPPORTED_PUBLIC_SOURCE.value,
            confidence_score=90,
        )
    ]
    session.add(record)
    session.commit()
    result = OpportunityScoringService(session).score(record, profile())

    assert result.score >= 70
    assert result.label == "High potential match"
    assert result.opportunity_status == "potential_opportunity"
    assert result.metadata == {"confirmed_vacancy": False}
    assert "potential-opportunity" in result.breakdown.explanation
    assert record.opportunity_score == result.score
    assert record.opportunity_score_breakdown["weights_total"] == 100


def test_low_relevance_and_missing_data_are_conservative() -> None:
    result = OpportunityScoringService().score(
        company(
            description=None,
            technology_focus=[],
            company_stage=None,
            research_status="not_researched",
        ),
        profile(
            skills=[],
            experience=[],
            projects=[],
            preferred_roles=[],
        ),
    )

    assert result.score == 0
    assert result.label == "Needs further research"
    assert result.breakdown.missing_information


def test_verified_contact_adds_accessibility_but_unverified_does_not() -> None:
    verified_company = company()
    verified_company.contacts = [
        Contact(
            name="Founder",
            email_verification_status=ContactVerificationStatus.SUPPORTED_PUBLIC_SOURCE.value,
            confidence_score=90,
        )
    ]
    unverified_company = company()
    unverified_company.contacts = [
        Contact(
            name="Unknown",
            email_verification_status=ContactVerificationStatus.UNVERIFIED.value,
            confidence_score=90,
        )
    ]

    verified = OpportunityScoringService().score(verified_company, profile())
    unverified = OpportunityScoringService().score(unverified_company, profile())
    assert verified.score > unverified.score


def test_research_evidence_improves_activity_and_quality() -> None:
    record = company(research_status="not_researched", description=None, technology_focus=[])
    research = CompanyResearch(
        company_id=record.id,
        activity_signals=[
            ResearchClaim(
                claim="Launched a new product",
                status=ClaimStatus.VERIFIED,
                source_urls=["https://acme.example/news"],
            )
        ],
        status=ResearchStatus.COMPLETED,
    )
    result = OpportunityScoringService().score(record, profile(), research=research)
    activity = next(f for f in result.breakdown.factors if f.name == "activity_signals")
    assert activity.score == 50
    assert activity.evidence[0].source_url == "https://acme.example/news"


def test_weights_are_configurable_and_must_total_100() -> None:
    with pytest.raises(ValueError):
        ScoringWeights(technical_relevance=50)
    weights = ScoringWeights(
        technical_relevance=50,
        role_relevance=10,
        engineering_need=10,
        activity_signals=10,
        contact_accessibility=10,
        research_quality=10,
    )
    result = OpportunityScoringService(weights=weights).score(company(), profile())
    assert next(f for f in result.breakdown.factors if f.name == "technical_relevance").weight == 50
    assert result.breakdown.weights_total == 100


def test_score_boundaries_and_recalculation(session: Session) -> None:
    record = company()
    session.add(record)
    session.commit()
    first = OpportunityScoringService(session).score(record, profile())
    record.technology_focus = []
    second = OpportunityScoringService(session).score(record, profile(skills=[]))
    assert 0 <= first.score <= 100
    assert 0 <= second.score <= 100
    assert first.score != second.score
