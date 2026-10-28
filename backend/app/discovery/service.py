from collections.abc import Sequence
from datetime import datetime, timezone
import re
from typing import Any
from urllib.parse import urlparse
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import func
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from app.discovery.extraction import extract_company_from_result
from app.discovery.planner import QueryPlanner
from app.discovery.providers import SearchProvider
from app.discovery.schemas import ResearchFilters, SearchResult
from app.models import Company, CompanySource, ResearchResult, ResearchRun


class DiscoverySummary(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    research_run_id: UUID
    status: str
    queries: list[str]
    total_results: int
    unique_companies_found: int
    company_ids: list[UUID] = Field(default_factory=list)
    errors: list[str] = Field(default_factory=list)


class DiscoveryService:
    """Orchestrates provider queries and atomically persists discovery output."""

    def __init__(
        self,
        session: Session,
        provider: SearchProvider,
        *,
        planner: QueryPlanner | None = None,
    ) -> None:
        self._session = session
        self._provider = provider
        self._planner = planner or QueryPlanner()

    def discover(self, filters: ResearchFilters) -> DiscoverySummary:
        queries = self._planner.plan(filters)
        run = ResearchRun(
            query="\n".join(queries),
            filters=filters.model_dump(mode="json"),
            status="running",
            started_at=datetime.now(timezone.utc),
            total_results=0,
            unique_companies_found=0,
            errors=[],
        )
        self._session.add(run)
        self._session.commit()

        results, errors = self._collect_results(queries, filters)
        try:
            company_ids = self._persist_results(run.id, results, filters=filters)
        except SQLAlchemyError as exc:
            self._session.rollback()
            message = "Database error while persisting discovery results."
            errors.append(message)
            self._finish_run(
                run.id,
                status="failed",
                total_results=0,
                company_ids=[],
                errors=errors,
            )
            raise RuntimeError(message) from exc

        status = "partial" if errors else "completed"
        self._finish_run(
            run.id,
            status=status,
            total_results=len(results),
            company_ids=company_ids,
            errors=errors,
        )
        return DiscoverySummary(
            research_run_id=run.id,
            status=status,
            queries=queries,
            total_results=len(results),
            unique_companies_found=len(company_ids),
            company_ids=company_ids,
            errors=errors,
        )

    def _collect_results(
        self,
        queries: Sequence[str],
        filters: ResearchFilters,
    ) -> tuple[list[SearchResult], list[str]]:
        results: list[SearchResult] = []
        errors: list[str] = []
        seen_urls: set[str] = set()
        for query in queries:
            try:
                query_results = self._provider.search([query], filters=filters)
            except RuntimeError as exc:
                errors.append(f"Search failed for query {query!r}: {exc}")
                continue
            for result in query_results:
                url = str(result.url)
                if url not in seen_urls:
                    seen_urls.add(url)
                    results.append(result)
        return results, errors

    def _persist_results(
        self,
        run_id: UUID,
        results: Sequence[SearchResult],
        *,
        filters: ResearchFilters | None = None,
    ) -> list[UUID]:
        company_ids: list[UUID] = []
        run = self._session.get(ResearchRun, run_id)
        if run is None:
            raise RuntimeError("Research run no longer exists.")

        seen_domains: set[str] = set()
        seen_names: set[str] = set()

        for result in results:
            extracted = extract_company_from_result(
                result,
                default_industry=filters.industry if filters else None,
                default_location=filters.country_or_region if filters else None,
                default_stage=filters.startup_stage if filters else None,
                target_technologies=filters.technologies if filters else None,
            )
            if extracted is None:
                continue

            if (
                extracted.canonical_domain in seen_domains
                or extracted.name.lower() in seen_names
            ):
                continue
            seen_domains.add(extracted.canonical_domain)
            seen_names.add(extracted.name.lower())

            company = (
                self._session.query(Company)
                .filter(
                    (Company.canonical_domain == extracted.canonical_domain)
                    | (func.lower(Company.name) == extracted.name.lower())
                )
                .first()
            )
            if company is None:
                company = Company(
                    name=extracted.name,
                    canonical_domain=extracted.canonical_domain,
                    website_url=extracted.website_url,
                    description=extracted.description,
                    industry=extracted.industry,
                    location=extracted.location,
                    company_stage=extracted.company_stage,
                    hiring_status=extracted.hiring_status,
                    technology_focus=extracted.technology_focus,
                )
                self._session.add(company)
                self._session.flush()
            else:
                # Enrich existing record
                if not company.website_url and extracted.website_url:
                    company.website_url = extracted.website_url
                if not company.description and extracted.description:
                    company.description = extracted.description
                if not company.industry and extracted.industry:
                    company.industry = extracted.industry
                if not company.location and extracted.location:
                    company.location = extracted.location
                if not company.company_stage and extracted.company_stage:
                    company.company_stage = extracted.company_stage
                if company.hiring_status in (None, "not_specified") and extracted.hiring_status:
                    company.hiring_status = extracted.hiring_status
                if extracted.technology_focus:
                    merged = list(dict.fromkeys((company.technology_focus or []) + extracted.technology_focus))
                    company.technology_focus = merged

            if company.id not in company_ids:
                company_ids.append(company.id)

            existing_source = (
                self._session.query(CompanySource)
                .filter_by(company_id=company.id, source_url=str(result.url))
                .first()
            )
            if existing_source is None:
                source = CompanySource(
                    company=company,
                    source_type=result.provider_name,
                    source_url=str(result.url),
                    title=result.title,
                    evidence_text=result.snippet,
                    published_at=result.published_at,
                )
                self._session.add(source)

            existing_rr = (
                self._session.query(ResearchResult)
                .filter_by(research_run_id=run.id, company_id=company.id)
                .first()
            )
            if existing_rr is None:
                self._session.add(
                    ResearchResult(
                        research_run=run,
                        company=company,
                        discovery_source=result.provider_name,
                    )
                )

        self._session.commit()
        return company_ids

    def _finish_run(
        self,
        run_id: UUID,
        *,
        status: str,
        total_results: int,
        company_ids: Sequence[UUID],
        errors: Sequence[str],
    ) -> None:
        run = self._session.get(ResearchRun, run_id)
        if run is None:
            raise RuntimeError("Research run no longer exists.")
        run.status = status
        run.completed_at = datetime.now(timezone.utc)
        run.total_results = total_results
        run.unique_companies_found = len(company_ids)
        run.errors = [{"message": error} for error in errors]
        self._session.commit()


def canonical_domain(url: str) -> str | None:
    """Return a lowercase registrable hostname key without a ``www`` prefix."""
    hostname = urlparse(str(url)).hostname
    if not hostname:
        return None
    normalized = hostname.rstrip(".").lower()
    return normalized.removeprefix("www.") or None
