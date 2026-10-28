from typing import Protocol

from app.contacts.schemas import ContactResearchResult
from app.models import Company


class ContactResearchProvider(Protocol):
    """Retrieves permitted public identity and contact evidence."""

    @property
    def name(self) -> str:
        """Provider identifier stored with contact source evidence."""

    def research_contacts(self, company: Company) -> ContactResearchResult:
        """Return only publicly supported contacts; never guess contact data."""
