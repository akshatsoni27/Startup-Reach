from collections.abc import Sequence
from datetime import datetime, timezone
from html.parser import HTMLParser
from typing import Protocol
from uuid import UUID

import httpx

from app.models import Company
from app.research.schemas import (
    ClaimStatus,
    CompanyResearch,
    ResearchClaim,
    ResearchStatus,
    SourceReference,
)


class CompanyResearchProvider(Protocol):
    """Retrieves permitted public company information."""

    @property
    def name(self) -> str:
        """Provider identifier stored with source evidence."""

    def research(self, company: Company) -> CompanyResearch:
        """Return sourced company claims without inventing missing information."""


class WebsiteResearchProviderError(RuntimeError):
    """Base error for public website retrieval failures."""


class WebsiteResearchProvider:
    """Fetches and extracts conservative facts from a company's public website."""

    def __init__(
        self,
        *,
        client: httpx.Client | None = None,
        timeout_seconds: float = 15.0,
    ) -> None:
        self._client = client
        self._timeout_seconds = timeout_seconds
        self._owns_client = client is None

    @property
    def name(self) -> str:
        return "official_website"

    def research(self, company: Company) -> CompanyResearch:
        if not company.website_url:
            return CompanyResearch(
                company_id=company.id,
                status=ResearchStatus.UNAVAILABLE,
                errors=["Company website URL is unavailable."],
            )

        client = self._client or httpx.Client(timeout=self._timeout_seconds)
        try:
            try:
                response = client.get(company.website_url)
            except httpx.TimeoutException as exc:
                raise WebsiteResearchProviderError(
                    "Company website request timed out."
                ) from exc
            except httpx.RequestError as exc:
                raise WebsiteResearchProviderError(
                    "Company website request failed."
                ) from exc
            if response.status_code >= 400:
                raise WebsiteResearchProviderError(
                    f"Company website returned HTTP {response.status_code}."
                )
            return self._extract(company.id, company.website_url, response.text)
        finally:
            if self._owns_client:
                client.close()

    def _extract(self, company_id: UUID, url: str, html: str) -> CompanyResearch:
        parser = _PublicPageParser()
        parser.feed(html)
        parser.close()
        if not parser.content:
            return CompanyResearch(
                company_id=company_id,
                status=ResearchStatus.PARTIAL,
                errors=["Company website contained no usable public text."],
            )

        retrieved_at = datetime.now(timezone.utc)
        source = SourceReference(
            url=url,
            title=parser.title,
            evidence_text=parser.content,
            retrieved_at=retrieved_at,
        )
        overview_text = parser.description or parser.title
        overview = (
            ResearchClaim(
                claim=overview_text,
                status=ClaimStatus.VERIFIED,
                source_urls=[url],
            )
            if overview_text
            else None
        )
        return CompanyResearch(
            company_id=company_id,
            overview=overview,
            sources=[source],
            status=ResearchStatus.COMPLETED if overview else ResearchStatus.PARTIAL,
            errors=[] if overview else ["No overview could be extracted."],
        )


class _PublicPageParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.title: str | None = None
        self.description: str | None = None
        self.content = ""
        self._in_title = False
        self._in_script_or_style = False
        self._title_parts: list[str] = []
        self._description_parts: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag == "title":
            self._in_title = True
        if tag in {"script", "style", "noscript"}:
            self._in_script_or_style = True
        if tag == "meta":
            attributes = dict(attrs)
            if attributes.get("name", "").lower() == "description":
                content = attributes.get("content", "")
                if content:
                    self._description_parts.append(content.strip())

    def handle_endtag(self, tag: str) -> None:
        if tag == "title":
            self._in_title = False
        if tag in {"script", "style", "noscript"}:
            self._in_script_or_style = False

    def handle_data(self, data: str) -> None:
        text = " ".join(data.split())
        if not text or self._in_script_or_style:
            return
        if self._in_title:
            self._title_parts.append(text)
        else:
            self.content = " ".join((self.content, text)).strip()

    def close(self) -> None:
        super().close()
        self.title = " ".join(self._title_parts).strip() or None
        self.description = " ".join(self._description_parts).strip() or None
