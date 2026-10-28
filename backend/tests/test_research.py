from collections.abc import Callable
from uuid import uuid4

import httpx
import pytest
from sqlalchemy import create_engine, event, select
from sqlalchemy.orm import Session

from app.models import Base, Company, CompanySource
from app.research.providers import WebsiteResearchProvider
from app.research.schemas import (
    ClaimStatus,
    CompanyResearch,
    ResearchClaim,
    ResearchStatus,
    SourceReference,
)
from app.research.service import CompanyResearchService


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


def company(website_url: str | None = "https://acme.example") -> Company:
    return Company(
        id=uuid4(),
        name="Acme",
        website_url=website_url,
        canonical_domain="acme.example" if website_url else None,
        technology_focus=[],
    )


def test_website_provider_extracts_sourced_overview() -> None:
    client = httpx.Client(
        transport=httpx.MockTransport(
            lambda request: httpx.Response(
                200,
                text=(
                    "<html><head><title>Acme AI</title>"
                    '<meta name="description" content="Acme builds workflow software.">'
                    "</head><body><p>Public product information.</p></body></html>"
                ),
            )
        )
    )
    record = company()

    research = WebsiteResearchProvider(client=client).research(record)

    assert research.status == ResearchStatus.COMPLETED
    assert research.overview is not None
    assert research.overview.status == ClaimStatus.VERIFIED
    assert research.overview.claim == "Acme builds workflow software."
    assert str(research.sources[0].url) == "https://acme.example/"


def test_website_provider_handles_missing_and_empty_sites() -> None:
    missing = WebsiteResearchProvider().research(company(None))
    assert missing.status == ResearchStatus.UNAVAILABLE

    client = httpx.Client(
        transport=httpx.MockTransport(lambda request: httpx.Response(200, text="<html></html>"))
    )
    empty = WebsiteResearchProvider(client=client).research(company())
    assert empty.status == ResearchStatus.PARTIAL
    assert empty.sources == []


def test_website_provider_handles_http_and_timeout_errors() -> None:
    error_client = httpx.Client(
        transport=httpx.MockTransport(lambda request: httpx.Response(503))
    )
    with pytest.raises(RuntimeError, match="HTTP 503"):
        WebsiteResearchProvider(client=error_client).research(company())

    def timeout(request: httpx.Request) -> httpx.Response:
        raise httpx.ReadTimeout("timeout", request=request)

    timeout_client = httpx.Client(transport=httpx.MockTransport(timeout))
    with pytest.raises(RuntimeError, match="timed out"):
        WebsiteResearchProvider(client=timeout_client).research(company())


class FakeResearchProvider:
    name = "mock_research"

    def __init__(self, research: CompanyResearch) -> None:
        self.research_result = research

    def research(self, company: Company) -> CompanyResearch:
        return self.research_result


def test_research_service_persists_claim_sources_and_preserves_existing_description(
    session: Session,
) -> None:
    record = company()
    record.description = "Existing verified description"
    session.add(record)
    session.commit()
    source = SourceReference(
        url="https://acme.example/product",
        title="Product",
        evidence_text="Acme product evidence",
        retrieved_at=__import__("datetime").datetime.now(__import__("datetime").timezone.utc),
    )
    research = CompanyResearch(
        company_id=record.id,
        overview=ResearchClaim(
            claim="Weaker replacement",
            status=ClaimStatus.INFERENCE,
            source_urls=[source.url],
        ),
        products_and_services=[
            ResearchClaim(
                claim="Workflow automation",
                status=ClaimStatus.VERIFIED,
                source_urls=[source.url],
            )
        ],
        technical_context=[
            ResearchClaim(
                claim="Python",
                status=ClaimStatus.VERIFIED,
                source_urls=[source.url],
            )
        ],
        activity_signals=[],
        sources=[source],
        status=ResearchStatus.COMPLETED,
    )

    result = CompanyResearchService(session, FakeResearchProvider(research)).research(record)

    refreshed = session.get(Company, record.id)
    assert result.status == ResearchStatus.COMPLETED
    assert refreshed is not None
    assert refreshed.description == "Existing verified description"
    assert refreshed.technology_focus == ["Python"]
    assert refreshed.research_status == "completed"
    assert len(session.scalars(select(CompanySource)).all()) == 1


def test_research_service_handles_partial_results_and_deduplicates_sources(
    session: Session,
) -> None:
    record = company()
    session.add(record)
    session.commit()
    source = SourceReference(
        url="https://acme.example",
        evidence_text="Evidence",
        retrieved_at=__import__("datetime").datetime.now(__import__("datetime").timezone.utc),
    )
    research = CompanyResearch(
        company_id=record.id,
        sources=[source],
        products_and_services=[
            ResearchClaim(
                claim="Same evidence",
                status=ClaimStatus.INFERENCE,
                source_urls=[source.url],
            )
        ],
        status=ResearchStatus.PARTIAL,
    )
    service = CompanyResearchService(session, FakeResearchProvider(research))

    service.research(record)
    service.research(record)

    assert session.get(Company, record.id).research_status == "partial"
    assert len(session.scalars(select(CompanySource)).all()) == 1
