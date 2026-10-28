from collections.abc import Sequence
from typing import Any

import httpx

from app.config import Settings, get_settings
from app.discovery.normalization import normalize_search_results
from app.discovery.schemas import ResearchFilters, SearchResult

TAVILY_SEARCH_URL = "https://api.tavily.com/search"


class TavilyError(RuntimeError):
    """Base error for a failed Tavily search operation."""


class TavilyConfigurationError(TavilyError):
    """Raised when Tavily is invoked without required configuration."""


class TavilyTimeoutError(TavilyError):
    """Raised when Tavily does not respond before the configured timeout."""


class TavilyRateLimitError(TavilyError):
    """Raised when Tavily rejects a request because of rate limiting."""


class TavilyProviderError(TavilyError):
    """Raised when Tavily returns a non-success response."""


class TavilyResponseError(TavilyError):
    """Raised when Tavily returns an unexpected successful response."""


class TavilySearchProvider:
    """Tavily adapter implementing the provider-neutral search contract."""

    def __init__(
        self,
        *,
        settings: Settings | None = None,
        client: httpx.Client | None = None,
    ) -> None:
        self._settings = settings or get_settings()
        self._client = client
        self._owns_client = client is None

    @property
    def name(self) -> str:
        return "tavily"

    def search(
        self,
        queries: Sequence[str],
        *,
        filters: ResearchFilters,
    ) -> list[SearchResult]:
        del filters  # Tavily receives the already planned, provider-neutral queries.
        api_key = self._api_key()
        cleaned_queries = [query.strip() for query in queries if query.strip()]
        if not cleaned_queries:
            return []

        client = self._client or httpx.Client(timeout=self._settings.tavily_timeout_seconds)
        try:
            raw_results: list[dict[str, Any]] = []
            for query in cleaned_queries:
                raw_results.extend(self._search_query(client, query, api_key))
            return normalize_search_results(raw_results, provider_name=self.name)
        finally:
            if self._owns_client:
                client.close()

    def _api_key(self) -> str:
        if self._settings.tavily_api_key is None:
            raise TavilyConfigurationError(
                "Tavily is not configured. Set TAVILY_API_KEY on the backend."
            )
        return self._settings.tavily_api_key.get_secret_value()

    def _search_query(
        self,
        client: httpx.Client,
        query: str,
        api_key: str,
    ) -> list[dict[str, Any]]:
        payload = {
            "api_key": api_key,
            "query": query,
            "search_depth": "basic",
            "include_answer": False,
            "include_raw_content": False,
            "exclude_domains": [
                "indeed.com",
                "topgenaijobs.com",
                "dice.com",
                "builtin.com",
                "glassdoor.com",
                "ziprecruiter.com",
                "capitalonecareers.com",
                "ai.engineer",
                "youtube.com",
                "facebook.com",
                "twitter.com",
                "linkedin.com",
            ],
        }
        try:
            response = client.post(TAVILY_SEARCH_URL, json=payload)
        except httpx.TimeoutException as exc:
            raise TavilyTimeoutError("Tavily search timed out.") from exc
        except httpx.RequestError as exc:
            raise TavilyProviderError("Tavily search request failed.") from exc

        if response.status_code == 429:
            raise TavilyRateLimitError("Tavily rate limit reached.")
        if response.status_code >= 400:
            raise TavilyProviderError(
                f"Tavily search failed with HTTP {response.status_code}."
            )

        try:
            data = response.json()
        except ValueError as exc:
            raise TavilyResponseError("Tavily returned invalid JSON.") from exc

        results = data.get("results") if isinstance(data, dict) else None
        if not isinstance(results, list):
            raise TavilyResponseError("Tavily response did not contain a results list.")
        normalized_payloads: list[dict[str, Any]] = []
        for result in results:
            if not isinstance(result, dict):
                continue
            metadata = {}
            if "score" in result:
                metadata["score"] = result["score"]
            normalized_payloads.append(
                {
                    "title": result.get("title"),
                    "url": result.get("url"),
                    "snippet": result.get("content"),
                    "published_at": result.get("published_date"),
                    "metadata": metadata or None,
                }
            )
        return normalized_payloads
