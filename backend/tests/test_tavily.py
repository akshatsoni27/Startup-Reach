from collections.abc import Callable

import httpx
import pytest
from pydantic import SecretStr

from app.config import Settings
from app.discovery.schemas import ResearchFilters
from app.discovery.tavily import (
    TavilyConfigurationError,
    TavilyProviderError,
    TavilyRateLimitError,
    TavilyResponseError,
    TavilySearchProvider,
    TavilyTimeoutError,
)


def make_provider(handler: Callable[[httpx.Request], httpx.Response]) -> TavilySearchProvider:
    client = httpx.Client(transport=httpx.MockTransport(handler))
    settings = Settings(
        database_url="postgresql+psycopg://user:password@localhost/db",
        tavily_api_key=SecretStr("test-tavily-key"),
    )
    return TavilySearchProvider(settings=settings, client=client)


def test_tavily_maps_successful_results_and_sends_each_query() -> None:
    requests: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        return httpx.Response(
            200,
            json={
                "results": [
                    {
                        "title": "Example startup",
                        "url": "https://example.com",
                        "content": "Builds useful software.",
                        "published_date": "2026-02-03",
                        "score": 0.9,
                    }
                ]
            },
        )

    provider = make_provider(handler)
    results = provider.search(
        ["AI startups in Berlin", "AI startups in Berlin"],
        filters=ResearchFilters(industry="AI"),
    )

    assert len(requests) == 2
    assert results[0].title == "Example startup"
    assert results[0].snippet == "Builds useful software."
    assert results[0].published_at is not None
    assert results[0].metadata == {"score": 0.9}
    assert requests[0].url == "https://api.tavily.com/search"
    assert requests[0].content.find(b"test-tavily-key") >= 0


def test_tavily_skips_malformed_records_without_fabricating_results() -> None:
    provider = make_provider(
        lambda request: httpx.Response(
            200,
            json={
                "results": [
                    {"title": "Missing URL", "content": "Not usable"},
                    {"title": "Valid", "url": "https://valid.example", "content": "Evidence"},
                ]
            },
        )
    )

    results = provider.search(["query"], filters=ResearchFilters(keywords=["AI"]))

    assert [result.title for result in results] == ["Valid"]


def test_tavily_missing_credentials_is_checked_at_invocation() -> None:
    settings = Settings(
        database_url="postgresql+psycopg://user:password@localhost/db",
        tavily_api_key=None,
    )
    provider = TavilySearchProvider(settings=settings)

    with pytest.raises(TavilyConfigurationError, match="TAVILY_API_KEY"):
        provider.search(["query"], filters=ResearchFilters(keywords=["AI"]))


@pytest.mark.parametrize(
    ("status_code", "exception_type"),
    [(429, TavilyRateLimitError), (500, TavilyProviderError)],
)
def test_tavily_http_errors_are_sanitized(status_code: int, exception_type: type[Exception]) -> None:
    provider = make_provider(lambda request: httpx.Response(status_code, text="secret error"))

    with pytest.raises(exception_type) as error:
        provider.search(["query"], filters=ResearchFilters(keywords=["AI"]))

    assert "secret error" not in str(error.value)
    assert "test-tavily-key" not in str(error.value)


def test_tavily_rejects_unexpected_response_shape() -> None:
    provider = make_provider(lambda request: httpx.Response(200, json={"answer": "not results"}))

    with pytest.raises(TavilyResponseError, match="results list"):
        provider.search(["query"], filters=ResearchFilters(keywords=["AI"]))


def test_tavily_maps_timeout_and_network_errors() -> None:
    def timeout_handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ReadTimeout("timed out", request=request)

    timeout_provider = make_provider(timeout_handler)
    with pytest.raises(TavilyTimeoutError):
        timeout_provider.search(["query"], filters=ResearchFilters(keywords=["AI"]))

    def network_handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("unavailable", request=request)

    network_provider = make_provider(network_handler)
    with pytest.raises(TavilyProviderError):
        network_provider.search(["query"], filters=ResearchFilters(keywords=["AI"]))
