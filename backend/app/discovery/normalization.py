from collections.abc import Mapping, Sequence
from typing import Any

from pydantic import ValidationError

from app.discovery.schemas import SearchResult


def normalize_search_result(
    raw_result: Mapping[str, Any],
    *,
    provider_name: str,
) -> SearchResult | None:
    """Normalize one provider payload; malformed or empty records are discarded."""
    if not raw_result:
        return None

    payload = {
        "title": raw_result.get("title"),
        "url": raw_result.get("url"),
        "snippet": raw_result.get("snippet", raw_result.get("description")),
        "provider_name": provider_name,
        "published_at": raw_result.get("published_at"),
        "metadata": raw_result.get("metadata"),
    }
    try:
        return SearchResult.model_validate(payload)
    except ValidationError:
        return None


def normalize_search_results(
    raw_results: Sequence[Mapping[str, Any]],
    *,
    provider_name: str,
) -> list[SearchResult]:
    normalized: list[SearchResult] = []
    seen_urls: set[str] = set()
    for raw_result in raw_results:
        result = normalize_search_result(raw_result, provider_name=provider_name)
        if result is None or str(result.url) in seen_urls:
            continue
        seen_urls.add(str(result.url))
        normalized.append(result)
    return normalized
