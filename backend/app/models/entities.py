from datetime import datetime
from uuid import UUID

from sqlalchemy import (
    JSON,
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, TimestampMixin, UUIDPrimaryKeyMixin


class UserProfile(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "user_profiles"

    name: Mapped[str] = mapped_column(String(200), nullable=False)
    email: Mapped[str] = mapped_column(String(320), nullable=False, unique=True)
    portfolio_url: Mapped[str | None] = mapped_column(String(2048))
    resume_text: Mapped[str | None] = mapped_column(Text)
    skills: Mapped[list[str]] = mapped_column(JSON, nullable=False, default=list)
    experience: Mapped[list[dict[str, object]]] = mapped_column(
        JSON, nullable=False, default=list
    )
    projects: Mapped[list[dict[str, object]]] = mapped_column(
        JSON, nullable=False, default=list
    )
    preferred_roles: Mapped[list[str]] = mapped_column(JSON, nullable=False, default=list)
    preferred_locations: Mapped[list[str]] = mapped_column(
        JSON, nullable=False, default=list
    )
    preferred_industries: Mapped[list[str]] = mapped_column(
        JSON, nullable=False, default=list
    )


class Company(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "companies"
    __table_args__ = (
        Index("ix_companies_name", "name"),
        Index("ix_companies_country", "country"),
        Index("ix_companies_industry", "industry"),
        Index("ix_companies_opportunity_score", "opportunity_score"),
        CheckConstraint(
            "opportunity_score IS NULL OR "
            "(opportunity_score >= 0 AND opportunity_score <= 100)",
            name="ck_companies_opportunity_score_range",
        ),
    )

    name: Mapped[str] = mapped_column(String(300), nullable=False)
    canonical_domain: Mapped[str | None] = mapped_column(
        String(255), nullable=True, unique=True
    )
    website_url: Mapped[str | None] = mapped_column(String(2048))
    description: Mapped[str | None] = mapped_column(Text)
    industry: Mapped[str | None] = mapped_column(String(200))
    technology_focus: Mapped[list[str]] = mapped_column(JSON, nullable=False, default=list)
    location: Mapped[str | None] = mapped_column(String(300))
    country: Mapped[str | None] = mapped_column(String(100))
    company_stage: Mapped[str | None] = mapped_column(String(100))
    founding_year: Mapped[int | None] = mapped_column(Integer)
    team_size: Mapped[int | None] = mapped_column(Integer)
    hiring_status: Mapped[str | None] = mapped_column(String(100))
    opportunity_status: Mapped[str] = mapped_column(
        String(50), nullable=False, default="potential_opportunity"
    )
    opportunity_score: Mapped[int | None] = mapped_column(Integer)
    opportunity_score_breakdown: Mapped[dict[str, object]] = mapped_column(
        JSON, nullable=False, default=dict
    )
    research_status: Mapped[str] = mapped_column(
        String(50), nullable=False, default="not_researched"
    )
    last_researched_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    contacts: Mapped[list["Contact"]] = relationship(
        back_populates="company", cascade="all, delete-orphan"
    )
    sources: Mapped[list["CompanySource"]] = relationship(
        back_populates="company", cascade="all, delete-orphan"
    )
    research_results: Mapped[list["ResearchResult"]] = relationship(
        back_populates="company", cascade="all, delete-orphan"
    )
    email_drafts: Mapped[list["EmailDraft"]] = relationship(
        back_populates="company", cascade="all, delete-orphan"
    )
    outreach_activities: Mapped[list["OutreachActivity"]] = relationship(
        back_populates="company", cascade="all, delete-orphan"
    )


class Contact(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "contacts"
    __table_args__ = (
        Index("ix_contacts_company_id", "company_id"),
        Index("ix_contacts_email", "email"),
        CheckConstraint(
            "confidence_score IS NULL OR "
            "(confidence_score >= 0 AND confidence_score <= 100)",
            name="ck_contacts_confidence_score_range",
        ),
    )

    company_id: Mapped[UUID] = mapped_column(
        ForeignKey("companies.id", ondelete="CASCADE"), nullable=False
    )
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    role: Mapped[str | None] = mapped_column(String(150))
    email: Mapped[str | None] = mapped_column(String(320))
    email_verification_status: Mapped[str | None] = mapped_column(String(100))
    professional_profile_url: Mapped[str | None] = mapped_column(String(2048))
    company_contact_url: Mapped[str | None] = mapped_column(String(2048))
    confidence_score: Mapped[int | None] = mapped_column(Integer)
    research_status: Mapped[str] = mapped_column(
        String(50), nullable=False, default="not_researched"
    )

    company: Mapped["Company"] = relationship(back_populates="contacts")
    sources: Mapped[list["ContactSource"]] = relationship(
        back_populates="contact", cascade="all, delete-orphan"
    )
    email_drafts: Mapped[list["EmailDraft"]] = relationship(back_populates="contact")
    outreach_activities: Mapped[list["OutreachActivity"]] = relationship(
        back_populates="contact"
    )


class CompanySource(UUIDPrimaryKeyMixin, Base):
    __tablename__ = "company_sources"
    __table_args__ = (
        UniqueConstraint("company_id", "source_url", name="uq_company_sources_company_url"),
        Index("ix_company_sources_company_id", "company_id"),
    )

    company_id: Mapped[UUID] = mapped_column(
        ForeignKey("companies.id", ondelete="CASCADE"), nullable=False
    )
    source_type: Mapped[str] = mapped_column(String(100), nullable=False)
    source_url: Mapped[str] = mapped_column(String(2048), nullable=False)
    title: Mapped[str | None] = mapped_column(String(500))
    evidence_text: Mapped[str | None] = mapped_column(Text)
    published_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    retrieved_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )

    company: Mapped["Company"] = relationship(back_populates="sources")


class ContactSource(UUIDPrimaryKeyMixin, Base):
    __tablename__ = "contact_sources"
    __table_args__ = (
        UniqueConstraint("contact_id", "source_url", name="uq_contact_sources_contact_url"),
        Index("ix_contact_sources_contact_id", "contact_id"),
    )

    contact_id: Mapped[UUID] = mapped_column(
        ForeignKey("contacts.id", ondelete="CASCADE"), nullable=False
    )
    source_url: Mapped[str] = mapped_column(String(2048), nullable=False)
    evidence_text: Mapped[str | None] = mapped_column(Text)
    retrieved_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )

    contact: Mapped["Contact"] = relationship(back_populates="sources")


class ResearchRun(UUIDPrimaryKeyMixin, Base):
    __tablename__ = "research_runs"
    __table_args__ = (
        Index("ix_research_runs_status", "status"),
        Index("ix_research_runs_started_at", "started_at"),
    )

    query: Mapped[str] = mapped_column(Text, nullable=False)
    filters: Mapped[dict[str, object]] = mapped_column(JSON, nullable=False, default=dict)
    status: Mapped[str] = mapped_column(String(50), nullable=False, default="pending")
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    total_results: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    unique_companies_found: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    errors: Mapped[list[dict[str, object]]] = mapped_column(JSON, nullable=False, default=list)

    results: Mapped[list["ResearchResult"]] = relationship(
        back_populates="research_run", cascade="all, delete-orphan"
    )


class ResearchResult(UUIDPrimaryKeyMixin, Base):
    __tablename__ = "research_results"
    __table_args__ = (
        UniqueConstraint(
            "research_run_id", "company_id", name="uq_research_results_run_company"
        ),
        Index("ix_research_results_research_run_id", "research_run_id"),
        Index("ix_research_results_company_id", "company_id"),
    )

    research_run_id: Mapped[UUID] = mapped_column(
        ForeignKey("research_runs.id", ondelete="CASCADE"), nullable=False
    )
    company_id: Mapped[UUID] = mapped_column(
        ForeignKey("companies.id", ondelete="CASCADE"), nullable=False
    )
    discovery_source: Mapped[str] = mapped_column(String(100), nullable=False)
    relevance_score: Mapped[int | None] = mapped_column(Integer)

    research_run: Mapped["ResearchRun"] = relationship(back_populates="results")
    company: Mapped["Company"] = relationship(back_populates="research_results")


class EmailDraft(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "email_drafts"
    __table_args__ = (
        Index("ix_email_drafts_company_id", "company_id"),
        Index("ix_email_drafts_status", "status"),
        CheckConstraint(
            "status IN ('draft', 'ready_to_send', 'archived')",
            name="ck_email_drafts_status",
        ),
    )

    company_id: Mapped[UUID] = mapped_column(
        ForeignKey("companies.id", ondelete="CASCADE"), nullable=False
    )
    contact_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("contacts.id", ondelete="SET NULL")
    )
    subject: Mapped[str] = mapped_column(String(500), nullable=False)
    body: Mapped[str] = mapped_column(Text, nullable=False)
    personalization_evidence: Mapped[list[str]] = mapped_column(
        JSON, nullable=False, default=list
    )
    status: Mapped[str] = mapped_column(String(50), nullable=False, default="draft")

    company: Mapped["Company"] = relationship(back_populates="email_drafts")
    contact: Mapped["Contact | None"] = relationship(back_populates="email_drafts")
    outreach_activities: Mapped[list["OutreachActivity"]] = relationship(
        back_populates="email_draft"
    )


class OutreachActivity(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "outreach_activities"
    __table_args__ = (
        Index("ix_outreach_activities_company_id", "company_id"),
        Index("ix_outreach_activities_status", "status"),
    )

    company_id: Mapped[UUID] = mapped_column(
        ForeignKey("companies.id", ondelete="CASCADE"), nullable=False
    )
    contact_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("contacts.id", ondelete="SET NULL")
    )
    email_draft_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("email_drafts.id", ondelete="SET NULL")
    )
    status: Mapped[str] = mapped_column(String(50), nullable=False, default="planned")
    notes: Mapped[str | None] = mapped_column(Text)
    contacted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    follow_up_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    response_received_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    company: Mapped["Company"] = relationship(back_populates="outreach_activities")
    contact: Mapped["Contact | None"] = relationship(back_populates="outreach_activities")
    email_draft: Mapped["EmailDraft | None"] = relationship(
        back_populates="outreach_activities"
    )
