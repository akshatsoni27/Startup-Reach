from collections.abc import Generator
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.exc import OperationalError
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from app.api.v1 import db_session
from app.config import get_settings
from app.models import Base, Company, EmailDraft, ResearchRun
from app.security import require_auth
from main import app


@pytest.fixture()
def client(monkeypatch: pytest.MonkeyPatch) -> Generator[TestClient, None, None]:
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    factory = sessionmaker(bind=engine, autoflush=False, autocommit=False)

    def override_db() -> Generator[Session, None, None]:
        with factory() as session:
            yield session

    monkeypatch.setenv("STARTUPREACH_API_TOKEN", "valid-token-12345")
    get_settings.cache_clear()
    app.dependency_overrides.pop(require_auth, None)
    app.dependency_overrides[db_session] = override_db
    yield TestClient(app, raise_server_exceptions=False)
    app.dependency_overrides.clear()
    Base.metadata.drop_all(engine)
    get_settings.cache_clear()


def test_cors_allowed_origin(client: TestClient) -> None:
    response = client.get(
        "/api/v1/health",
        headers={"Origin": "http://localhost:5173"},
    )
    assert response.status_code == 200
    assert response.headers.get("access-control-allow-origin") == "http://localhost:5173"


def test_cors_unapproved_origin(client: TestClient) -> None:
    response = client.get(
        "/api/v1/health",
        headers={"Origin": "http://unapproved-origin.com"},
    )
    assert response.status_code == 200
    assert "access-control-allow-origin" not in response.headers


def test_cors_preflight_options(client: TestClient) -> None:
    response = client.options(
        "/api/v1/dashboard/summary",
        headers={
            "Origin": "http://localhost:5173",
            "Access-Control-Request-Method": "GET",
            "Access-Control-Request-Headers": "Authorization, Content-Type",
        },
    )
    assert response.status_code == 200
    assert response.headers.get("access-control-allow-origin") == "http://localhost:5173"
    assert "GET" in response.headers.get("access-control-allow-methods", "")


def test_cors_error_response_contains_cors_headers(client: TestClient) -> None:
    # 401 error with allowed origin
    response = client.get(
        "/api/v1/dashboard/summary",
        headers={"Origin": "http://localhost:5173"},
    )
    assert response.status_code == 401
    assert response.headers.get("access-control-allow-origin") == "http://localhost:5173"
    assert response.json()["code"] == "authentication_required"


def test_dashboard_summary_missing_token(client: TestClient) -> None:
    response = client.get("/api/v1/dashboard/summary")
    assert response.status_code == 401
    assert response.json() == {
        "code": "authentication_required",
        "message": "Authentication required.",
    }


def test_dashboard_summary_invalid_token(client: TestClient) -> None:
    response = client.get(
        "/api/v1/dashboard/summary",
        headers={"Authorization": "Bearer invalid-token"},
    )
    assert response.status_code == 401
    assert response.json() == {
        "code": "authentication_required",
        "message": "Invalid authentication credentials.",
    }


def test_dashboard_summary_valid_token_database_available(client: TestClient) -> None:
    # Seed data
    db_gen = app.dependency_overrides[db_session]()
    session = next(db_gen)
    try:
        company = Company(
            id=uuid4(),
            name="Test Corp",
            opportunity_score=85,
            technology_focus=["AI"],
        )
        session.add(company)
        session.commit()
    finally:
        db_gen.close()

    response = client.get(
        "/api/v1/dashboard/summary",
        headers={
            "Authorization": "Bearer valid-token-12345",
            "Origin": "http://localhost:5173",
        },
    )
    assert response.status_code == 200
    assert response.headers.get("access-control-allow-origin") == "http://localhost:5173"
    data = response.json()
    assert data["company_count"] == 1
    assert data["high_potential_company_count"] == 1
    assert len(data["recent_companies"]) == 1
    assert data["recent_companies"][0]["name"] == "Test Corp"


def test_dashboard_summary_database_unavailable(client: TestClient) -> None:
    def broken_db() -> Generator[Session, None, None]:
        raise OperationalError("failed to resolve host", params=None, orig=Exception("getaddrinfo failed"))
        yield  # pragma: no cover

    app.dependency_overrides[db_session] = broken_db

    response = client.get(
        "/api/v1/dashboard/summary",
        headers={
            "Authorization": "Bearer valid-token-12345",
            "Origin": "http://localhost:5173",
        },
    )
    assert response.status_code == 503
    assert response.headers.get("access-control-allow-origin") == "http://localhost:5173"
    assert "X-Request-ID" in response.headers
    data = response.json()
    assert data["code"] == "service_unavailable"
    assert data["message"] == "The database operation could not be completed."
    # Ensure sensitive details are not leaked
    assert "getaddrinfo" not in response.text
    assert "OperationalError" not in response.text
    assert "resolve" not in response.text
