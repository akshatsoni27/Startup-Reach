from app.discovery.schemas import ResearchFilters


class QueryPlanner:
    """Build deterministic, provider-independent startup research queries."""

    def plan(self, filters: ResearchFilters) -> list[str]:
        if not filters.has_criteria:
            raise ValueError("at least one research filter is required")

        context = self._context(filters)
        queries = [
            f"{context} startup companies building products",
            f"{context} emerging startup product launch",
            f"{context} startup founders product technology",
        ]
        return list(dict.fromkeys(queries))

    @staticmethod
    def _context(filters: ResearchFilters) -> str:
        parts: list[str] = []
        if filters.country_or_region:
            parts.append(filters.country_or_region)
        if filters.industry:
            parts.append(filters.industry)
        if filters.technologies:
            parts.append(" ".join(filters.technologies))
        if filters.startup_stage:
            parts.append(filters.startup_stage)
        if filters.company_size:
            parts.append(f"{filters.company_size} team")
        if filters.keywords:
            parts.extend(filters.keywords)
        return " ".join(parts)
