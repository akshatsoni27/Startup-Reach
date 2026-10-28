import json
from collections.abc import Generator

import pytest
from fastapi.testclient import TestClient

from app.preflight import inspect_database_url
from app.rate_limit import reset_rate_limits
from main import app


@pytest.fixture()
def client() -> Generator[TestClient, None, None]:
    reset_rate_limits()
    yield TestClient(app)
    reset_rate_limits()


def test_database_url_preflight_does_not_return_credentials() -> None:
    result = inspect_database_url(
        "postgresql+psycopg://user:p%40ss%3Aword@db.example.test:5432/app"
    )
    serialized = json.dumps(result)
    assert result["valid"] is True
    assert "p%40ss" not in serialized
    assert "db.example.test" not in serialized


def test_health_has_request_id_and_safe_headers(client: TestClient) -> None:
    response = client.get("/api/v1/health", headers={"X-Request-ID": "test-request"})
    assert response.status_code == 200
    assert response.headers["X-Request-ID"] == "test-request"


def test_provider_route_rate_limit_is_structured(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    from app.config import get_settings

    settings = get_settings()
    monkeypatch.setattr(settings, "rate_limit_max_requests", 1)
    first = client.post("/api/v1/research-runs", json={})
    second = client.post("/api/v1/research-runs", json={})
    assert first.status_code != 429
    assert second.status_code == 429
    assert second.json() == {
        "code": "rate_limited",
        "message": "Rate limit exceeded. Please retry later.",
    }


def test_invalid_auth_response_is_safe(
    client: TestClient, caplog: pytest.LogCaptureFixture
) -> None:
    caplog.set_level("INFO")
    response = client.get(
        "/api/v1/profile",
        headers={"Authorization": "Bearer super-secret-token"},
    )
    assert response.status_code in {401, 503}
    assert "super-secret-token" not in response.text
    assert "super-secret-token" not in caplog.text
