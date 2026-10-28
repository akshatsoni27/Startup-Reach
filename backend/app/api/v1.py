from collections.abc import Generator
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import AnyHttpUrl, BaseModel, ConfigDict, Field
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError, SQLAlchemyError
from sqlalchemy.orm import Session

from app.contacts.providers import ContactResearchProvider
from app.contacts.schemas import ContactResearchResult
from app.contacts.service import ContactResearchService
from app.db import get_db
from app.discovery.schemas import ResearchFilters
from app.discovery.service import DiscoveryService
from app.discovery.tavily import TavilySearchProvider
from app.drafting.schemas import DraftRequest, DraftResponse, DraftStatus
from app.drafting.service import EmailDraftingService
from app.models import (
    Company,
    CompanySource,
    Contact,
    ContactSource,
    EmailDraft,
    ResearchResult,
    ResearchRun,
    UserProfile,
)
from app.research.providers import CompanyResearchProvider, WebsiteResearchProvider
from app.research.schemas import CompanyResearch
from app.research.service import CompanyResearchService
from app.scoring.schemas import OpportunityScore
from app.scoring.service import OpportunityScoringService
from app.security import require_auth

router = APIRouter(prefix="/api/v1", dependencies=[Depends(require_auth)])


class ProfilePayload(BaseModel):
    model_config = ConfigDict(extra="forbid", from_attributes=True)

    name: str = Field(min_length=1, max_length=200)
    email: str = Field(min_length=3, max_length=320)
    portfolio_url: AnyHttpUrl | None = None
    resume_text: str | None = None
    skills: list[str] = Field(default_factory=list)
    experience: list[dict[str, object]] = Field(default_factory=list)
    projects: list[dict[str, object]] = Field(default_factory=list)
    preferred_roles: list[str] = Field(default_factory=list)
    preferred_locations: list[str] = Field(default_factory=list)
    preferred_industries: list[str] = Field(default_factory=list)


class CompanyResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    name: str
    canonical_domain: str | None
    website_url: str | None
    description: str | None
    industry: str | None
    technology_focus: list[str]
    location: str | None
    country: str | None
    company_stage: str | None
    hiring_status: str | None
    opportunity_status: str
    opportunity_score: int | None
    opportunity_score_breakdown: dict[str, object]
    research_status: str
    last_researched_at: object | None


class CompanyListResponse(BaseModel):
    items: list[CompanyResponse]
    page: int
    page_size: int
    total: int


class ContactResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    company_id: UUID
    name: str
    role: str | None
    email: str | None
    email_verification_status: str | None
    professional_profile_url: str | None
    company_contact_url: str | None
    confidence_score: int | None
    research_status: str


class DraftListResponse(BaseModel):
    items: list[DraftResponse]
    page: int
    page_size: int
    total: int


class DraftEditPayload(BaseModel):
    model_config = ConfigDict(extra="forbid")

    subject: str | None = Field(default=None, min_length=1, max_length=500)
    body: str | None = Field(default=None, min_length=1)
    status: DraftStatus | None = None


class DraftStatusPayload(BaseModel):
    status: DraftStatus


class CompanySourceResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    source_type: str
    source_url: str
    title: str | None
    evidence_text: str | None


class ResearchRunResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    query: str
    status: str
    total_results: int
    unique_companies_found: int
    errors: list[dict[str, object]]


class DashboardSummaryResponse(BaseModel):
    company_count: int
    high_potential_company_count: int
    draft_count: int
    research_run_count: int
    recent_companies: list[CompanyResponse]
    recent_research_runs: list[ResearchRunResponse]


class UnavailableContactProvider:
    name = "unavailable"

    def research_contacts(self, company: Company) -> ContactResearchResult:
        return ContactResearchResult(
            company_id=company.id,
            status="unavailable",
            errors=["No contact research provider is configured."],
        )


def db_session() -> Generator[Session, None, None]:
    yield from get_db()


def search_provider() -> TavilySearchProvider:
    return TavilySearchProvider()


def company_research_provider() -> WebsiteResearchProvider:
    return WebsiteResearchProvider()


def contact_research_provider() -> ContactResearchProvider:
    return UnavailableContactProvider()


def require_profile(session: Session) -> UserProfile:
    try:
        profile = session.scalar(select(UserProfile).order_by(UserProfile.created_at))
    except SQLAlchemyError as exc:
        raise safe_service_error(exc) from exc
    if profile is None:
        raise HTTPException(status_code=404, detail="User profile not found.")
    return profile


def get_company_or_404(session: Session, company_id: UUID) -> Company:
    company = session.get(Company, company_id)
    if company is None:
        raise HTTPException(status_code=404, detail="Company not found.")
    return company


def get_contact_or_404(session: Session, contact_id: UUID) -> Contact:
    contact = session.get(Contact, contact_id)
    if contact is None:
        raise HTTPException(status_code=404, detail="Contact not found.")
    return contact


def get_draft_or_404(session: Session, draft_id: UUID) -> EmailDraft:
    draft = session.get(EmailDraft, draft_id)
    if draft is None:
        raise HTTPException(status_code=404, detail="Email draft not found.")
    return draft


def safe_service_error(exc: Exception) -> HTTPException:
    if isinstance(exc, ValueError):
        return HTTPException(status_code=400, detail="The request could not be processed.")
    if isinstance(exc, IntegrityError):
        return HTTPException(
            status_code=409,
            detail="The requested record conflicts with existing data.",
        )
    if isinstance(exc, SQLAlchemyError):
        return HTTPException(status_code=503, detail="The database operation could not be completed.")
    return HTTPException(status_code=502, detail="The requested provider operation failed.")


@router.post("/profile", response_model=ProfilePayload, status_code=status.HTTP_201_CREATED)
def create_profile(payload: ProfilePayload, session: Annotated[Session, Depends(db_session)]) -> UserProfile:
    if session.scalar(select(UserProfile)):
        raise HTTPException(status_code=409, detail="A user profile already exists.")
    profile = UserProfile(**payload.model_dump(mode="json"))
    session.add(profile)
    try:
        session.commit()
        session.refresh(profile)
    except SQLAlchemyError as exc:
        session.rollback()
        raise safe_service_error(exc) from exc
    return profile


@router.get("/profile", response_model=ProfilePayload)
def read_profile(session: Annotated[Session, Depends(db_session)]) -> UserProfile:
    return require_profile(session)


@router.put("/profile", response_model=ProfilePayload)
def update_profile(
    payload: ProfilePayload, session: Annotated[Session, Depends(db_session)]
) -> UserProfile:
    profile = require_profile(session)
    for key, value in payload.model_dump(mode="json").items():
        setattr(profile, key, value)
    try:
        session.commit()
        session.refresh(profile)
    except SQLAlchemyError as exc:
        session.rollback()
        raise safe_service_error(exc) from exc
    return profile


@router.post("/research-runs", response_model=object, status_code=status.HTTP_201_CREATED)
def start_discovery(
    filters: ResearchFilters,
    session: Annotated[Session, Depends(db_session)],
    provider: Annotated[TavilySearchProvider, Depends(search_provider)],
) -> object:
    try:
        return DiscoveryService(session, provider).discover(filters)
    except Exception as exc:
        if exc.__class__.__name__ == "TavilyConfigurationError":
            raise HTTPException(status_code=503, detail="Search provider is not configured.") from exc
        raise safe_service_error(exc) from exc


@router.get("/research-runs", response_model=list[ResearchRunResponse])
def list_research_runs(session: Annotated[Session, Depends(db_session)]) -> list[ResearchRun]:
    return list(session.scalars(select(ResearchRun).order_by(ResearchRun.started_at.desc())).all())


@router.get("/dashboard/summary", response_model=DashboardSummaryResponse)
def dashboard_summary(
    session: Annotated[Session, Depends(db_session)],
) -> DashboardSummaryResponse:
    try:
        company_count = session.scalar(select(func.count()).select_from(Company)) or 0
        high_potential_company_count = (
            session.scalar(
                select(func.count())
                .select_from(Company)
                .where(Company.opportunity_score >= 75)
            )
            or 0
        )
        draft_count = session.scalar(select(func.count()).select_from(EmailDraft)) or 0
        research_run_count = session.scalar(select(func.count()).select_from(ResearchRun)) or 0
        recent_companies = list(
            session.scalars(
                select(Company).order_by(Company.created_at.desc()).limit(5)
            ).all()
        )
        recent_research_runs = list(
            session.scalars(
                select(ResearchRun).order_by(ResearchRun.started_at.desc()).limit(5)
            ).all()
        )
    except SQLAlchemyError as exc:
        raise safe_service_error(exc) from exc

    return DashboardSummaryResponse(
        company_count=company_count,
        high_potential_company_count=high_potential_company_count,
        draft_count=draft_count,
        research_run_count=research_run_count,
        recent_companies=recent_companies,
        recent_research_runs=recent_research_runs,
    )


@router.get("/research-runs/{run_id}", response_model=ResearchRunResponse)
def read_research_run(run_id: UUID, session: Annotated[Session, Depends(db_session)]) -> ResearchRun:
    run = session.get(ResearchRun, run_id)
    if run is None:
        raise HTTPException(status_code=404, detail="Research run not found.")
    return run


@router.get("/companies", response_model=CompanyListResponse)
def list_companies(
    session: Annotated[Session, Depends(db_session)],
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
) -> CompanyListResponse:
    total = session.scalar(select(func.count()).select_from(Company)) or 0
    items = list(
        session.scalars(
            select(Company)
            .order_by(Company.created_at.desc())
            .offset((page - 1) * page_size)
            .limit(page_size)
        ).all()
    )
    return CompanyListResponse(items=items, page=page, page_size=page_size, total=total)


@router.get("/companies/{company_id}", response_model=CompanyResponse)
def read_company(company_id: UUID, session: Annotated[Session, Depends(db_session)]) -> Company:
    return get_company_or_404(session, company_id)


@router.get("/companies/{company_id}/sources", response_model=list[CompanySourceResponse])
def list_company_sources(company_id: UUID, session: Annotated[Session, Depends(db_session)]) -> list[CompanySource]:
    get_company_or_404(session, company_id)
    return list(session.scalars(select(CompanySource).where(CompanySource.company_id == company_id)).all())


@router.post("/companies/{company_id}/research", response_model=CompanyResearch)
def research_company(
    company_id: UUID,
    session: Annotated[Session, Depends(db_session)],
    provider: Annotated[CompanyResearchProvider, Depends(company_research_provider)],
) -> CompanyResearch:
    company = get_company_or_404(session, company_id)
    try:
        result = CompanyResearchService(session, provider).research(company)
        if result.errors:
            result = result.model_copy(update={"errors": ["Company research provider failed."]})
        return result
    except Exception as exc:
        raise safe_service_error(exc) from exc


@router.get("/companies/{company_id}/contacts", response_model=list[ContactResponse])
def list_contacts(company_id: UUID, session: Annotated[Session, Depends(db_session)]) -> list[Contact]:
    get_company_or_404(session, company_id)
    return list(session.scalars(select(Contact).where(Contact.company_id == company_id)).all())


@router.post("/companies/{company_id}/contacts/research", response_model=ContactResearchResult)
def research_contacts(
    company_id: UUID,
    session: Annotated[Session, Depends(db_session)],
    provider: Annotated[ContactResearchProvider, Depends(contact_research_provider)],
) -> ContactResearchResult:
    company = get_company_or_404(session, company_id)
    try:
        return ContactResearchService(session, provider).research(company)
    except Exception as exc:
        raise safe_service_error(exc) from exc


@router.post("/companies/{company_id}/score", response_model=OpportunityScore)
def score_company(company_id: UUID, session: Annotated[Session, Depends(db_session)]) -> OpportunityScore:
    company = get_company_or_404(session, company_id)
    profile = require_profile(session)
    try:
        return OpportunityScoringService(session).score(company, profile)
    except Exception as exc:
        raise safe_service_error(exc) from exc


@router.post("/companies/{company_id}/drafts", response_model=DraftResponse, status_code=status.HTTP_201_CREATED)
def create_draft(
    company_id: UUID,
    payload: DraftRequest,
    session: Annotated[Session, Depends(db_session)],
) -> DraftResponse:
    company = get_company_or_404(session, company_id)
    if payload.company_id != company.id:
        raise HTTPException(status_code=400, detail="Draft company does not match URL.")
    profile = require_profile(session)
    contact = session.get(Contact, payload.contact_id) if payload.contact_id else None
    if payload.contact_id and (contact is None or contact.company_id != company.id):
        raise HTTPException(status_code=404, detail="Contact not found for this company.")
    try:
        return EmailDraftingService(session).generate(profile, company, contact=contact, draft_request=payload)
    except Exception as exc:
        raise safe_service_error(exc) from exc


@router.get("/drafts", response_model=DraftListResponse)
def list_drafts(
    session: Annotated[Session, Depends(db_session)],
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
) -> DraftListResponse:
    total = session.scalar(select(func.count()).select_from(EmailDraft)) or 0
    drafts = list(
        session.scalars(
            select(EmailDraft)
            .order_by(EmailDraft.created_at.desc())
            .offset((page - 1) * page_size)
            .limit(page_size)
        ).all()
    )
    return DraftListResponse(
        items=[EmailDraftingService(session)._to_response(draft) for draft in drafts],
        page=page,
        page_size=page_size,
        total=total,
    )


@router.get("/drafts/{draft_id}", response_model=DraftResponse)
def read_draft(draft_id: UUID, session: Annotated[Session, Depends(db_session)]) -> DraftResponse:
    return EmailDraftingService(session)._to_response(get_draft_or_404(session, draft_id))


@router.put("/drafts/{draft_id}", response_model=DraftResponse)
def edit_draft(
    draft_id: UUID,
    payload: DraftEditPayload,
    session: Annotated[Session, Depends(db_session)],
) -> DraftResponse:
    try:
        return EmailDraftingService(session).edit(
            draft_id, subject=payload.subject, body=payload.body, status=payload.status
        )
    except Exception as exc:
        if isinstance(exc, ValueError) and str(exc) == "Email draft was not found.":
            raise HTTPException(status_code=404, detail=str(exc)) from exc
        raise safe_service_error(exc) from exc


@router.post("/drafts/{draft_id}/regenerate", response_model=DraftResponse)
def regenerate_draft(
    draft_id: UUID,
    session: Annotated[Session, Depends(db_session)],
) -> DraftResponse:
    draft = get_draft_or_404(session, draft_id)
    company = get_company_or_404(session, draft.company_id)
    profile = require_profile(session)
    contact = session.get(Contact, draft.contact_id) if draft.contact_id else None
    try:
        return EmailDraftingService(session).regenerate(
            draft_id, profile, company, contact=contact
        )
    except Exception as exc:
        raise safe_service_error(exc) from exc


@router.patch("/drafts/{draft_id}/status", response_model=DraftResponse)
def update_draft_status(
    draft_id: UUID,
    payload: DraftStatusPayload,
    session: Annotated[Session, Depends(db_session)],
) -> DraftResponse:
    try:
        return EmailDraftingService(session).edit(draft_id, status=payload.status)
    except Exception as exc:
        if isinstance(exc, ValueError) and str(exc) == "Email draft was not found.":
            raise HTTPException(status_code=404, detail=str(exc)) from exc
        raise safe_service_error(exc) from exc
