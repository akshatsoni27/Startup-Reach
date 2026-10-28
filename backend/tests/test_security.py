import os
from collections.abc import Generator

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from app.api.v1 import db_session
from app.config import get_settings
from app.models import Base
from app.security import require_auth
from main import app


@pytest.fixture()
def auth_client(monkeypatch: pytest.MonkeyPatch) -> Generator[TestClient, None, None]:
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

    monkeypatch.setenv("STARTUPREACH_API_TOKEN", "test-token")
    get_settings.cache_clear()
    app.dependency_overrides.pop(require_auth, None)
    app.dependency_overrides[db_session] = override_db
    yield TestClient(app)
    app.dependency_overrides.clear()
    Base.metadata.drop_all(engine)
    get_settings.cache_clear()


def test_health_is_public_but_api_is_protected(auth_client: TestClient) -> None:
    health = auth_client.get("/api/v1/health")
    protected = auth_client.get("/api/v1/profile")

    assert health.status_code == 200
    assert protected.status_code == 401
    assert protected.json() == {
        "code": "authentication_required",
        "message": "Authentication required.",
    }


def test_valid_and_invalid_bearer_tokens(auth_client: TestClient) -> None:
    invalid = auth_client.get(
        "/api/v1/profile", headers={"Authorization": "Bearer wrong-token"}
    )
    valid = auth_client.get(
        "/api/v1/profile", headers={"Authorization": "Bearer test-token"}
    )

    assert invalid.status_code == 401
    assert invalid.json()["code"] == "authentication_required"
    assert valid.status_code == 404
    assert valid.json() == {
        "code": "not_found",
        "message": "User profile not found.",
    }


def test_validation_errors_use_safe_consistent_shape(auth_client: TestClient) -> None:
    response = auth_client.post(
        "/api/v1/profile",
        headers={"Authorization": "Bearer test-token"},
        json={"name": "", "email": "not-an-email"},
    )

    assert response.status_code == 422
    assert response.json() == {
        "code": "validation_error",
        "message": "Request validation failed.",
    }


def test_missing_auth_configuration_is_not_exposed(
    auth_client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.delenv("STARTUPREACH_API_TOKEN", raising=False)
    get_settings.cache_clear()
    monkeypatch.setattr(get_settings(), "api_token", None)

    response = auth_client.get(
        "/api/v1/profile", headers={"Authorization": "Bearer test-token"}
    )

    assert response.status_code == 503
    assert response.json() == {
        "code": "service_unavailable",
        "message": "Authentication is not configured.",
    }
    assert "test-token" not in response.text

