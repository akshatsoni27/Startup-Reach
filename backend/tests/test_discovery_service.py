from collections.abc import Sequence

import pytest
from sqlalchemy import create_engine, event, select
from sqlalchemy.orm import Session

from app.discovery.schemas import ResearchFilters, SearchResult
from app.discovery.service import DiscoveryService
from app.models import Base, Company, CompanySource, ResearchResult, ResearchRun


class FakeProvider:
    name = "fake-provider"

    def __init__(
        self,
        results_by_query: dict[str, Sequence[SearchResult]],
        failures: dict[str, RuntimeError] | None = None,
    ) -> None:
        self.results_by_query = results_by_query
        self.failures = failures or {}
        self.queries: list[str] = []

    def search(self, queries, *, filters: ResearchFilters) -> list[SearchResult]:
        query = queries[0]
        self.queries.append(query)
        if query in self.failures:
            raise self.failures[query]
        return list(self.results_by_query.get(query, []))


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


def result(title: str, url: str, snippet: str = "Evidence") -> SearchResult:
    return SearchResult(
        title=title,
        url=url,
        snippet=snippet,
        provider_name="fake-provider",
    )


def test_success_persists_company_source_and_run_result(session: Session) -> None:
    provider = FakeProvider(
        {
            "AI startup companies building products": [
                result("Acme AI", "https://acme.ai/about")
            ],
            "AI emerging startup product launch": [],
            "AI startup founders product technology": [],
        }
    )

    summary = DiscoveryService(session, provider).discover(
        ResearchFilters(keywords=["AI"])
    )

    company = session.scalar(select(Company))
    run = session.get(ResearchRun, summary.research_run_id)
    assert summary.status == "completed"
    assert summary.total_results == 1
    assert summary.unique_companies_found == 1
    assert company is not None
    assert company.canonical_domain == "acme.ai"
    assert session.scalar(select(CompanySource)) is not None
    assert session.scalar(select(ResearchResult)) is not None
    assert run is not None and run.status == "completed"


def test_duplicate_domains_and_existing_company_are_reused(session: Session) -> None:
    existing = Company(
        name="Existing Acme",
        canonical_domain="acme.ai",
        technology_focus=[],
    )
    session.add(existing)
    session.commit()
    provider = FakeProvider(
        {
            "AI startup companies building products": [
                result("New title", "https://www.acme.ai/one"),
                result("Another title", "https://acme.ai/two"),
            ],
            "AI emerging startup product launch": [],
            "AI startup founders product technology": [],
        }
    )

    summary = DiscoveryService(session, provider).discover(
        ResearchFilters(keywords=["AI"])
    )

    assert summary.unique_companies_found == 1
    assert session.scalar(select(Company).where(Company.canonical_domain == "acme.ai")).name == "Existing Acme"
    assert len(session.scalars(select(Company)).all()) == 1
    assert len(session.scalars(select(CompanySource)).all()) == 1


def test_empty_results_complete_without_companies(session: Session) -> None:
    provider = FakeProvider({})

    summary = DiscoveryService(session, provider).discover(
        ResearchFilters(country_or_region="Singapore")
    )

    run = session.get(ResearchRun, summary.research_run_id)
    assert summary.status == "completed"
    assert summary.total_results == 0
    assert summary.unique_companies_found == 0
    assert run is not None and run.status == "completed"
    assert session.scalar(select(Company)) is None


def test_partial_provider_failure_persists_successful_results(session: Session) -> None:
    provider = FakeProvider(
        {
            "AI startup companies building products": [
                result("Good Company", "https://good.example")
            ]
        },
        failures={
            "AI emerging startup product launch": RuntimeError("temporary provider failure")
        },
    )

    summary = DiscoveryService(session, provider).discover(
        ResearchFilters(keywords=["AI"])
    )

    run = session.get(ResearchRun, summary.research_run_id)
    assert summary.status == "partial"
    assert summary.unique_companies_found == 1
    assert len(summary.errors) == 1
    assert run is not None and run.status == "partial"
    assert run.errors == [{"message": summary.errors[0]}]


def test_search_queries_are_run_independently(session: Session) -> None:
    provider = FakeProvider({})

    DiscoveryService(session, provider).discover(
        ResearchFilters(industry="climate technology")
    )

    assert len(provider.queries) == 3
