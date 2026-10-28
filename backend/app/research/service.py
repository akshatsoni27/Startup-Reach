from datetime import datetime, timezone
from uuid import UUID

from pydantic import AnyHttpUrl
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from app.models import Company, CompanySource
from app.research.providers import CompanyResearchProvider
from app.research.schemas import ClaimStatus, CompanyResearch, ResearchStatus


class CompanyResearchService:
    """Researches one existing company and persists only sourced improvements."""

    def __init__(self, session: Session, provider: CompanyResearchProvider) -> None:
        self._session = session
        self._provider = provider

    def research(self, company: Company) -> CompanyResearch:
        try:
            research = self._provider.research(company)
        except RuntimeError as exc:
            research = CompanyResearch(
                company_id=company.id,
                status=ResearchStatus.UNAVAILABLE,
                errors=[str(exc)],
            )

        try:
            self._persist(company, research)
        except SQLAlchemyError as exc:
            self._session.rollback()
            raise RuntimeError("Database error while persisting company research.") from exc
        return research

    def _persist(self, company: Company, research: CompanyResearch) -> None:
        if research.overview and research.overview.status == ClaimStatus.VERIFIED:
            if company.description is None and research.overview.claim:
                company.description = research.overview.claim

        verified_technology = [
            claim.claim
            for claim in research.technical_context
            if claim.status == ClaimStatus.VERIFIED and claim.claim
        ]
        if verified_technology:
            company.technology_focus = list(
                dict.fromkeys([*company.technology_focus, *verified_technology])
            )

        for source in research.sources:
            self._add_source_if_new(company, source)
        for claim in (
            research.products_and_services
            + research.technical_context
            + research.activity_signals
        ):
            for source_url in claim.source_urls:
                self._add_source_if_new(
                    company,
                    next(
                        (
                            source
                            for source in research.sources
                            if str(source.url) == str(source_url)
                        ),
                        None,
                    ),
                    evidence_text=claim.claim,
                )

        company.research_status = research.status.value
        company.last_researched_at = datetime.now(timezone.utc)
        self._session.commit()

    def _add_source_if_new(
        self,
        company: Company,
        source,
        *,
        evidence_text: str | None = None,
    ) -> None:
        if source is None:
            return
        source_url = str(source.url)
        existing = next(
            (item for item in company.sources if item.source_url == source_url),
            None,
        )
        if existing is not None:
            return
        self._session.add(
            CompanySource(
                company=company,
                source_type=self._provider.name,
                source_url=source_url,
                title=source.title,
                evidence_text=evidence_text or source.evidence_text,
            )
        )
