from collections.abc import Sequence
from uuid import uuid4

import pytest
from sqlalchemy import create_engine, event, select, func
from sqlalchemy.orm import Session

from app.discovery.extraction import extract_company_from_result, extract_company_name
from app.discovery.filtering import is_valid_startup_candidate
from app.discovery.schemas import ResearchFilters, SearchResult
from app.discovery.service import DiscoveryService
from app.models import Base, Company, CompanySource, ResearchResult, ResearchRun


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


class MockSearchProvider:
    name = "mock-provider"

    def __init__(self, results: Sequence[SearchResult]) -> None:
        self._results = list(results)

    def search(self, queries, *, filters: ResearchFilters) -> list[SearchResult]:
        return self._results


def make_result(title: str, url: str, snippet: str = "Evidence description") -> SearchResult:
    return SearchResult(
        title=title,
        url=url,
        snippet=snippet,
        provider_name="mock-provider",
    )


def test_reject_exact_examples_from_issue() -> None:
    # Example 1: Job board / job listing aggregator
    r1 = make_result(
        "LangGraph AI jobs · TopGenAIJobs",
        "https://topgenaijobs.com/jobs/skill/langgraph",
        "Search 100+ LangGraph AI jobs and find your next agentic role.",
    )
    valid1, reason1 = is_valid_startup_candidate(r1)
    assert valid1 is False
    assert "topgenaijobs.com" in reason1 or "job" in reason1

    # Example 2: Corporate job vacancy at large bank
    r2 = make_result(
        "Full Stack Engineer 4 – People Tech – GenAI & Agentic Systems at Capital One",
        "https://www.capitalonecareers.com/job/mclean/full-stack-engineer-4-people-tech-genai-and-agentic-systems/1732/101107274144",
        "Apply now for Full Stack Engineer 4 at Capital One in McLean, VA.",
    )
    valid2, reason2 = is_valid_startup_candidate(r2)
    assert valid2 is False
    assert "capitalone" in reason2 or "job" in reason2

    # Example 3: Event / conference schedule
    r3 = make_result(
        "Schedule | AI Engineer Europe 2026",
        "https://ai.engineer/europe/schedule",
        "Conference schedule, track sessions, keynote speakers, and tickets for AI Engineer Europe.",
    )
    valid3, reason3 = is_valid_startup_candidate(r3)
    assert valid3 is False
    assert "ai.engineer" in reason3 or "schedule" in reason3


def test_reject_course_and_listicle_results() -> None:
    # Course / tutorial
    course = make_result(
        "Agentic AI Full Course | Build Real World AI Agents with LangChain, LangGraph & CrewAI",
        "https://www.youtube.com/watch?v=MSsqjZ0_GpU",
        "Full course on building AI agents from scratch.",
    )
    valid_course, _ = is_valid_startup_candidate(course)
    assert valid_course is False

    # Listicle / aggregator
    listicle = make_result(
        "Top 5 AI Agent Development Companies in 2026",
        "https://neurons-lab.com/articles/ai-agent-development-services",
        "Here are the top 5 companies building agentic systems.",
    )
    valid_list, _ = is_valid_startup_candidate(listicle)
    assert valid_list is False


def test_accept_valid_startup_profiles() -> None:
    r_langchain = make_result(
        "LangChain: the open agent platform to own your intelligence",
        "https://www.langchain.com/",
        "LangChain is the open framework for building context-aware reasoning applications. We are hiring founding engineers.",
    )
    extracted = extract_company_from_result(r_langchain)
    assert extracted is not None
    assert extracted.name == "LangChain"
    assert extracted.canonical_domain == "langchain.com"
    assert extracted.website_url == "https://www.langchain.com"
    assert extracted.hiring_status == "actively_hiring"

    r_cognition = make_result(
        "Cognition | Introducing Devin",
        "https://cognition.ai/",
        "Cognition is an applied AI lab building Devin, the world's first fully autonomous AI software engineer.",
    )
    extracted_cognition = extract_company_from_result(r_cognition)
    assert extracted_cognition is not None
    assert extracted_cognition.name == "Cognition"
    assert extracted_cognition.canonical_domain == "cognition.ai"


def test_discovery_service_persists_only_valid_companies(session: Session) -> None:
    # Mixed results: 1 valid startup and 3 invalid results
    results = [
        make_result(
            "LangGraph AI jobs · TopGenAIJobs",
            "https://topgenaijobs.com/jobs/skill/langgraph",
            "Search jobs",
        ),
        make_result(
            "Full Stack Engineer 4 – People Tech – GenAI & Agentic Systems at Capital One",
            "https://www.capitalonecareers.com/job/123",
            "Apply now",
        ),
        make_result(
            "Schedule | AI Engineer Europe 2026",
            "https://ai.engineer/europe/schedule",
            "Conference sessions",
        ),
        make_result(
            "LangChain: the open agent platform to own your intelligence",
            "https://www.langchain.com/",
            "LangChain enables developers to build agentic workflows.",
        ),
    ]

    provider = MockSearchProvider(results)
    service = DiscoveryService(session, provider)
    summary = service.discover(ResearchFilters(keywords=["AI agents"]))

    # Summary should report only 1 unique valid company
    assert summary.unique_companies_found == 1
    assert len(summary.company_ids) == 1

    # Database should only contain the valid company
    persisted_companies = session.scalars(select(Company)).all()
    assert len(persisted_companies) == 1
    assert persisted_companies[0].name == "LangChain"
    assert persisted_companies[0].canonical_domain == "langchain.com"
    assert "topgenaijobs" not in [c.canonical_domain for c in persisted_companies]
    assert "capitalonecareers" not in [c.canonical_domain for c in persisted_companies]
    assert "ai.engineer" not in [c.canonical_domain for c in persisted_companies]


def test_deduplication_prevents_duplicate_company_creation(session: Session) -> None:
    # Two results for the same company with different titles and URLs
    results = [
        make_result(
            "LangChain: the open agent platform to own your intelligence",
            "https://www.langchain.com/",
            "LangChain framework.",
        ),
        make_result(
            "LangChain - Python and JavaScript Libraries",
            "https://langchain.com/docs",
            "Documentation for LangChain.",
        ),
    ]

    provider = MockSearchProvider(results)
    service = DiscoveryService(session, provider)
    summary = service.discover(ResearchFilters(keywords=["LangChain"]))

    assert summary.unique_companies_found == 1
    companies = session.scalars(select(Company)).all()
    assert len(companies) == 1
    assert companies[0].name == "LangChain"

    # Single unique company source is kept per deduplicated company in run
    sources = session.scalars(select(CompanySource)).all()
    assert len(sources) == 1


def test_invalid_results_do_not_count_toward_dashboard_totals(session: Session) -> None:
    # Run with only invalid results
    invalid_results = [
        make_result("Schedule | AI Engineer Europe 2026", "https://ai.engineer/europe/schedule"),
        make_result("LangGraph AI jobs · TopGenAIJobs", "https://topgenaijobs.com/jobs"),
    ]
    provider = MockSearchProvider(invalid_results)
    service = DiscoveryService(session, provider)
    summary = service.discover(ResearchFilters(keywords=["Europe AI"]))

    assert summary.unique_companies_found == 0
    assert summary.total_results == 2  # raw provider results collected

    # Total companies in DB must remain 0
    total = session.scalar(select(func.count()).select_from(Company))
    assert total == 0
