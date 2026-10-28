from pathlib import Path

from app.models import Base


def test_all_phase_two_tables_are_registered() -> None:
    expected_tables = {
        "user_profiles",
        "companies",
        "contacts",
        "company_sources",
        "contact_sources",
        "research_runs",
        "research_results",
        "email_drafts",
        "outreach_activities",
    }

    assert expected_tables == set(Base.metadata.tables)


def test_alembic_uses_model_metadata_and_initial_revision_exists() -> None:
    alembic_env = Path(__file__).parents[1] / "alembic" / "env.py"
    revision_files = list(
        (alembic_env.parent / "versions").glob("*_create_phase_2_data_models.py")
    )

    assert "target_metadata = Base.metadata" in alembic_env.read_text()
    assert len(revision_files) == 1
    revision = revision_files[0].read_text()
    assert "def upgrade()" in revision
    assert 'op.create_table(\n        "companies"' in revision
