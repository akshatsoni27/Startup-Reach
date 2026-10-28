from datetime import date
from typing import Any

from pydantic import AnyHttpUrl, BaseModel, ConfigDict, Field, field_validator


def _clean_text(value: str) -> str:
    cleaned = value.strip()
    if not cleaned:
        raise ValueError("values must not be blank")
    return cleaned


class ResearchFilters(BaseModel):
    """User-controlled criteria for global startup discovery."""

    model_config = ConfigDict(extra="forbid")

    country_or_region: str | None = None
    industry: str | None = None
    technologies: list[str] = Field(default_factory=list)
    startup_stage: str | None = None
    keywords: list[str] = Field(default_factory=list)
    company_size: str | None = None

    @field_validator(
        "country_or_region",
        "industry",
        "startup_stage",
        "company_size",
        mode="before",
    )
    @classmethod
    def validate_optional_text(cls, value: str | None) -> str | None:
        return None if value is None else _clean_text(value)

    @field_validator("technologies", "keywords", mode="before")
    @classmethod
    def validate_text_lists(cls, values: list[str] | None) -> list[str]:
        if values is None:
            return []
        return [_clean_text(value) for value in values]

    @field_validator("technologies", "keywords")
    @classmethod
    def remove_duplicates(cls, values: list[str]) -> list[str]:
        return list(dict.fromkeys(values))

    @property
    def has_criteria(self) -> bool:
        return any(
            (
                self.country_or_region,
                self.industry,
                self.technologies,
                self.startup_stage,
                self.keywords,
                self.company_size,
            )
        )


class SearchResult(BaseModel):
    """Provider-neutral, normalized result returned by a search adapter."""

    model_config = ConfigDict(extra="forbid")

    title: str = Field(min_length=1)
    url: AnyHttpUrl
    snippet: str = Field(min_length=1)
    provider_name: str = Field(min_length=1)
    published_at: date | None = None
    metadata: dict[str, Any] | None = None

    @field_validator("title", "snippet", "provider_name", mode="before")
    @classmethod
    def validate_text(cls, value: str) -> str:
        return _clean_text(value)
