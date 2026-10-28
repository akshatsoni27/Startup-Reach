from collections.abc import Sequence
from typing import Protocol

from app.discovery.schemas import ResearchFilters, SearchResult


class SearchProvider(Protocol):
    """Interface implemented by concrete web or directory search adapters."""

    @property
    def name(self) -> str:
        """Stable provider name used in normalized result metadata."""

    def search(
        self,
        queries: Sequence[str],
        *,
        filters: ResearchFilters,
    ) -> Sequence[SearchResult]:
        """Search without fabricating results and return normalized records."""
