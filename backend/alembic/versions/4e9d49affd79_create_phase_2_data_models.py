"""create phase 2 data models

Revision ID: 4e9d49affd79
Revises: 
Create Date: 2026-10-27 17:47:31.745806
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa



revision: str = '4e9d49affd79'
down_revision: Union[str, Sequence[str], None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "companies",
        sa.Column("id", sa.Uuid(as_uuid=True), nullable=False),
        sa.Column("name", sa.String(length=300), nullable=False),
        sa.Column("canonical_domain", sa.String(length=255), nullable=True),
        sa.Column("website_url", sa.String(length=2048), nullable=True),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("industry", sa.String(length=200), nullable=True),
        sa.Column("technology_focus", sa.JSON(), nullable=False),
        sa.Column("location", sa.String(length=300), nullable=True),
        sa.Column("country", sa.String(length=100), nullable=True),
        sa.Column("company_stage", sa.String(length=100), nullable=True),
        sa.Column("founding_year", sa.Integer(), nullable=True),
        sa.Column("team_size", sa.Integer(), nullable=True),
        sa.Column("hiring_status", sa.String(length=100), nullable=True),
        sa.Column(
            "opportunity_status",
            sa.String(length=50),
            nullable=False,
            server_default="potential_opportunity",
        ),
        sa.Column("opportunity_score", sa.Integer(), nullable=True),
        sa.Column("opportunity_score_breakdown", sa.JSON(), nullable=False),
        sa.Column(
            "research_status",
            sa.String(length=50),
            nullable=False,
            server_default="not_researched",
        ),
        sa.Column("last_researched_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.CheckConstraint(
            "opportunity_score IS NULL OR "
            "(opportunity_score >= 0 AND opportunity_score <= 100)",
            name="ck_companies_opportunity_score_range",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("canonical_domain"),
    )
    op.create_index("ix_companies_name", "companies", ["name"], unique=False)
    op.create_index("ix_companies_country", "companies", ["country"], unique=False)
    op.create_index("ix_companies_industry", "companies", ["industry"], unique=False)
    op.create_index(
        "ix_companies_opportunity_score", "companies", ["opportunity_score"], unique=False
    )

    op.create_table(
        "user_profiles",
        sa.Column("id", sa.Uuid(as_uuid=True), nullable=False),
        sa.Column("name", sa.String(length=200), nullable=False),
        sa.Column("email", sa.String(length=320), nullable=False),
        sa.Column("portfolio_url", sa.String(length=2048), nullable=True),
        sa.Column("resume_text", sa.Text(), nullable=True),
        sa.Column("skills", sa.JSON(), nullable=False),
        sa.Column("experience", sa.JSON(), nullable=False),
        sa.Column("projects", sa.JSON(), nullable=False),
        sa.Column("preferred_roles", sa.JSON(), nullable=False),
        sa.Column("preferred_locations", sa.JSON(), nullable=False),
        sa.Column("preferred_industries", sa.JSON(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("email"),
    )

    op.create_table(
        "contacts",
        sa.Column("id", sa.Uuid(as_uuid=True), nullable=False),
        sa.Column("company_id", sa.Uuid(as_uuid=True), nullable=False),
        sa.Column("name", sa.String(length=200), nullable=False),
        sa.Column("role", sa.String(length=150), nullable=True),
        sa.Column("email", sa.String(length=320), nullable=True),
        sa.Column("email_verification_status", sa.String(length=100), nullable=True),
        sa.Column("professional_profile_url", sa.String(length=2048), nullable=True),
        sa.Column("company_contact_url", sa.String(length=2048), nullable=True),
        sa.Column("confidence_score", sa.Integer(), nullable=True),
        sa.Column("research_status", sa.String(length=50), nullable=False, server_default="not_researched"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.CheckConstraint(
            "confidence_score IS NULL OR "
            "(confidence_score >= 0 AND confidence_score <= 100)",
            name="ck_contacts_confidence_score_range",
        ),
        sa.ForeignKeyConstraint(["company_id"], ["companies.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_contacts_company_id", "contacts", ["company_id"], unique=False)
    op.create_index("ix_contacts_email", "contacts", ["email"], unique=False)

    op.create_table(
        "company_sources",
        sa.Column("id", sa.Uuid(as_uuid=True), nullable=False),
        sa.Column("company_id", sa.Uuid(as_uuid=True), nullable=False),
        sa.Column("source_type", sa.String(length=100), nullable=False),
        sa.Column("source_url", sa.String(length=2048), nullable=False),
        sa.Column("title", sa.String(length=500), nullable=True),
        sa.Column("evidence_text", sa.Text(), nullable=True),
        sa.Column("published_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("retrieved_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["company_id"], ["companies.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("company_id", "source_url", name="uq_company_sources_company_url"),
    )
    op.create_index("ix_company_sources_company_id", "company_sources", ["company_id"], unique=False)

    op.create_table(
        "contact_sources",
        sa.Column("id", sa.Uuid(as_uuid=True), nullable=False),
        sa.Column("contact_id", sa.Uuid(as_uuid=True), nullable=False),
        sa.Column("source_url", sa.String(length=2048), nullable=False),
        sa.Column("evidence_text", sa.Text(), nullable=True),
        sa.Column("retrieved_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["contact_id"], ["contacts.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("contact_id", "source_url", name="uq_contact_sources_contact_url"),
    )
    op.create_index("ix_contact_sources_contact_id", "contact_sources", ["contact_id"], unique=False)

    op.create_table(
        "research_runs",
        sa.Column("id", sa.Uuid(as_uuid=True), nullable=False),
        sa.Column("query", sa.Text(), nullable=False),
        sa.Column("filters", sa.JSON(), nullable=False),
        sa.Column("status", sa.String(length=50), nullable=False, server_default="pending"),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("total_results", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("unique_companies_found", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("errors", sa.JSON(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_research_runs_status", "research_runs", ["status"], unique=False)
    op.create_index("ix_research_runs_started_at", "research_runs", ["started_at"], unique=False)

    op.create_table(
        "research_results",
        sa.Column("id", sa.Uuid(as_uuid=True), nullable=False),
        sa.Column("research_run_id", sa.Uuid(as_uuid=True), nullable=False),
        sa.Column("company_id", sa.Uuid(as_uuid=True), nullable=False),
        sa.Column("discovery_source", sa.String(length=100), nullable=False),
        sa.Column("relevance_score", sa.Integer(), nullable=True),
        sa.ForeignKeyConstraint(["company_id"], ["companies.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["research_run_id"], ["research_runs.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("research_run_id", "company_id", name="uq_research_results_run_company"),
    )
    op.create_index("ix_research_results_research_run_id", "research_results", ["research_run_id"], unique=False)
    op.create_index("ix_research_results_company_id", "research_results", ["company_id"], unique=False)

    op.create_table(
        "email_drafts",
        sa.Column("id", sa.Uuid(as_uuid=True), nullable=False),
        sa.Column("company_id", sa.Uuid(as_uuid=True), nullable=False),
        sa.Column("contact_id", sa.Uuid(as_uuid=True), nullable=True),
        sa.Column("subject", sa.String(length=500), nullable=False),
        sa.Column("body", sa.Text(), nullable=False),
        sa.Column("personalization_evidence", sa.JSON(), nullable=False),
        sa.Column("status", sa.String(length=50), nullable=False, server_default="draft"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.CheckConstraint(
            "status IN ('draft', 'ready_to_send', 'archived')",
            name="ck_email_drafts_status",
        ),
        sa.ForeignKeyConstraint(["company_id"], ["companies.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["contact_id"], ["contacts.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_email_drafts_company_id", "email_drafts", ["company_id"], unique=False)
    op.create_index("ix_email_drafts_status", "email_drafts", ["status"], unique=False)

    op.create_table(
        "outreach_activities",
        sa.Column("id", sa.Uuid(as_uuid=True), nullable=False),
        sa.Column("company_id", sa.Uuid(as_uuid=True), nullable=False),
        sa.Column("contact_id", sa.Uuid(as_uuid=True), nullable=True),
        sa.Column("email_draft_id", sa.Uuid(as_uuid=True), nullable=True),
        sa.Column("status", sa.String(length=50), nullable=False, server_default="planned"),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column("contacted_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("follow_up_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("response_received_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["company_id"], ["companies.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["contact_id"], ["contacts.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["email_draft_id"], ["email_drafts.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_outreach_activities_company_id", "outreach_activities", ["company_id"], unique=False)
    op.create_index("ix_outreach_activities_status", "outreach_activities", ["status"], unique=False)


def downgrade() -> None:
    op.drop_index("ix_outreach_activities_status", table_name="outreach_activities")
    op.drop_index("ix_outreach_activities_company_id", table_name="outreach_activities")
    op.drop_table("outreach_activities")
    op.drop_index("ix_email_drafts_status", table_name="email_drafts")
    op.drop_index("ix_email_drafts_company_id", table_name="email_drafts")
    op.drop_table("email_drafts")
    op.drop_index("ix_research_results_company_id", table_name="research_results")
    op.drop_index("ix_research_results_research_run_id", table_name="research_results")
    op.drop_table("research_results")
    op.drop_index("ix_research_runs_started_at", table_name="research_runs")
    op.drop_index("ix_research_runs_status", table_name="research_runs")
    op.drop_table("research_runs")
    op.drop_index("ix_contact_sources_contact_id", table_name="contact_sources")
    op.drop_table("contact_sources")
    op.drop_index("ix_company_sources_company_id", table_name="company_sources")
    op.drop_table("company_sources")
    op.drop_index("ix_contacts_email", table_name="contacts")
    op.drop_index("ix_contacts_company_id", table_name="contacts")
    op.drop_table("contacts")
    op.drop_index("ix_companies_opportunity_score", table_name="companies")
    op.drop_index("ix_companies_industry", table_name="companies")
    op.drop_index("ix_companies_country", table_name="companies")
    op.drop_index("ix_companies_name", table_name="companies")
    op.drop_table("user_profiles")
    op.drop_table("companies")
