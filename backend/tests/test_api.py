from collections.abc import Generator
from contextlib import contextmanager
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, event
from sqlalchemy.pool import StaticPool
from sqlalchemy.orm import Session, sessionmaker

from app.api.v1 import (
    company_research_provider,
    contact_research_provider,
    db_session,
)
from app.models import Base, Company, UserProfile
from app.security import require_auth
from main import app


@pytest.fixture()
def client() -> Generator[TestClient, None, None]:
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )

    @event.listens_for(engine, "connect")
    def enable_foreign_keys(dbapi_connection, _connection_record) -> None:
        dbapi_connection.execute("PRAGMA foreign_keys=ON")

    Base.metadata.create_all(engine)
    factory = sessionmaker(bind=engine, autoflush=False, autocommit=False)

    def override_db() -> Generator[Session, None, None]:
        with factory() as session:
            yield session

    app.dependency_overrides[db_session] = override_db
    app.dependency_overrides[require_auth] = lambda: None
    yield TestClient(app)
    app.dependency_overrides.clear()
    Base.metadata.drop_all(engine)


@contextmanager
def db_test_session() -> Generator[Session, None, None]:
    generator = app.dependency_overrides[db_session]()
    session = next(generator)
    try:
        yield session
    finally:
        generator.close()


def create_company(session: Session) -> Company:
    company = Company(
        id=uuid4(),
        name="Acme",
        canonical_domain="acme.example",
        website_url="https://acme.example",
        description="Acme builds software.",
        technology_focus=["Python"],
    )
    session.add(company)
    session.commit()
    return company


def test_profile_create_get_and_update(client: TestClient) -> None:
    payload = {
        "name": "Developer",
        "email": "developer@example.com",
        "skills": ["Python"],
        "experience": [],
        "projects": [],
        "preferred_roles": ["backend"],
        "preferred_locations": [],
        "preferred_industries": [],
    }
    created = client.post("/api/v1/profile", json=payload)
    assert created.status_code == 201
    assert client.get("/api/v1/profile").json()["name"] == "Developer"

    updated = client.put(
        "/api/v1/profile",
        json={**payload, "name": "Updated Developer"},
    )
    assert updated.status_code == 200
    assert updated.json()["name"] == "Updated Developer"


def test_company_list_is_paginated_and_not_found_is_structured(client: TestClient) -> None:
    with db_test_session() as session:
        create_company(session)

    response = client.get("/api/v1/companies?page=1&page_size=1")
    assert response.status_code == 200
    assert response.json()["page_size"] == 1
    assert response.json()["total"] == 1
    assert client.get(f"/api/v1/companies/{uuid4()}").status_code == 404


def test_dashboard_summary_uses_aggregates_and_persists_score_breakdown(
    client: TestClient,
) -> None:
    with db_test_session() as session:
        company = create_company(session)
        company.opportunity_score = 80
        company.opportunity_score_breakdown = {
            "factors": [{"name": "Technical relevance", "score": 90}],
            "weights_total": 100,
        }
        session.commit()

    summary = client.get("/api/v1/dashboard/summary")
    assert summary.status_code == 200
    assert summary.json()["company_count"] == 1
    assert summary.json()["high_potential_company_count"] == 1
    assert summary.json()["recent_companies"][0]["opportunity_score_breakdown"]["weights_total"] == 100


def test_draft_create_edit_status_and_regenerate(client: TestClient) -> None:
    profile_payload = {
        "name": "Developer",
        "email": "draft@example.com",
        "skills": ["Python"],
        "experience": [],
        "projects": [],
        "preferred_roles": [],
        "preferred_locations": [],
        "preferred_industries": [],
    }
    assert client.post("/api/v1/profile", json=profile_payload).status_code == 201

    with db_test_session() as session:
        company = create_company(session)
        company_id = str(company.id)

    created = client.post(
        f"/api/v1/companies/{company_id}/drafts",
        json={"company_id": company_id},
    )
    assert created.status_code == 201
    draft_id = created.json()["id"]
    assert created.json()["manual_only"] is True

    edited = client.put(
        f"/api/v1/drafts/{draft_id}",
        json={"subject": "Updated subject"},
    )
    assert edited.status_code == 200
    assert edited.json()["subject"]["text"] == "Updated subject"

    status_response = client.patch(
        f"/api/v1/drafts/{draft_id}/status",
        json={"status": "ready_to_send"},
    )
    assert status_response.status_code == 200
    assert status_response.json()["status"] == "ready_to_send"
    assert client.post(f"/api/v1/drafts/{draft_id}/regenerate").status_code == 200
    assert client.post(f"/api/v1/drafts/{draft_id}/send").status_code == 404


def test_provider_failures_are_safe_and_research_endpoints_exist(client: TestClient) -> None:
    class FakeResearchProvider:
        name = "fake"

        def research(self, company):
            raise RuntimeError("private provider details")

    class FakeContactProvider:
        name = "fake"

        def research_contacts(self, company):
            from app.contacts.schemas import ContactResearchResult

            return ContactResearchResult(
                company_id=company.id,
                status="unavailable",
                errors=["No provider configured."],
            )

    app.dependency_overrides[company_research_provider] = lambda: FakeResearchProvider()
    app.dependency_overrides[contact_research_provider] = lambda: FakeContactProvider()
    with db_test_session() as session:
        company = create_company(session)
        company_id = str(company.id)

    research = client.post(f"/api/v1/companies/{company_id}/research")
    assert research.status_code == 200
    assert research.json()["status"] == "unavailable"
    assert "private provider" not in research.text

    contacts = client.post(f"/api/v1/companies/{company_id}/contacts/research")
    assert contacts.status_code == 200
    assert contacts.json()["status"] == "unavailable"
