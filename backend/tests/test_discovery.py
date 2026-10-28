from datetime import date

import pytest
from pydantic import ValidationError

from app.discovery.normalization import normalize_search_results
from app.discovery.planner import QueryPlanner
from app.discovery.schemas import ResearchFilters, SearchResult


def test_query_planner_creates_global_non_job_queries() -> None:
    filters = ResearchFilters(
        country_or_region="Berlin, Germany",
        industry="developer tools",
        technologies=["Python", "AI agents"],
        startup_stage="seed",
        keywords=["workflow automation"],
        company_size="1-50",
    )

    queries = QueryPlanner().plan(filters)

    assert len(queries) == 3
    assert all("Berlin, Germany" in query for query in queries)
    assert all("developer tools" in query for query in queries)
    assert all("job" not in query.lower() for query in queries)
    assert "founders" in queries[2]


def test_query_planner_supports_partial_worldwide_filters() -> None:
    queries = QueryPlanner().plan(
        ResearchFilters(country_or_region="São Paulo, Brazil", keywords=["climate tech"])
    )

    assert queries
    assert all("São Paulo, Brazil" in query for query in queries)
    assert all("climate tech" in query for query in queries)


def test_query_planner_rejects_empty_filters() -> None:
    with pytest.raises(ValueError, match="at least one"):
        QueryPlanner().plan(ResearchFilters())


def test_filter_rejects_blank_values_and_unknown_fields() -> None:
    with pytest.raises(ValidationError):
        ResearchFilters(industry="   ")
    with pytest.raises(ValidationError):
        ResearchFilters(industry="AI", region="everywhere")


def test_search_result_normalization_accepts_description_and_date() -> None:
    results = normalize_search_results(
        [
            {
                "title": "A startup",
                "url": "https://example.com/startup",
                "description": "A product description.",
                "published_at": date(2026, 1, 2),
                "metadata": {"rank": 1},
            }
        ],
        provider_name="example-provider",
    )

    assert len(results) == 1
    assert isinstance(results[0], SearchResult)
    assert results[0].snippet == "A product description."
    assert results[0].provider_name == "example-provider"
    assert results[0].published_at == date(2026, 1, 2)


def test_normalization_skips_empty_invalid_and_duplicate_results() -> None:
    results = normalize_search_results(
        [
            {},
            {"title": "Missing URL", "snippet": "No URL"},
            {
                "title": "Valid",
                "url": "https://example.com",
                "snippet": "Useful evidence",
            },
            {
                "title": "Duplicate",
                "url": "https://example.com",
                "snippet": "Same URL",
            },
        ],
        provider_name="provider",
    )

    assert len(results) == 1
    assert str(results[0].url) == "https://example.com/"
