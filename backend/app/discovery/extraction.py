import re
from typing import NamedTuple
from urllib.parse import urlparse

from app.discovery.filtering import GENERIC_TITLES, is_valid_startup_candidate
from app.discovery.schemas import SearchResult


class ExtractedCompany(NamedTuple):
    name: str
    canonical_domain: str
    website_url: str
    description: str
    technology_focus: list[str]
    industry: str | None
    location: str | None
    company_stage: str | None
    hiring_status: str | None


def extract_company_name(title: str, hostname: str) -> str | None:
    """Extract a concise, normalized company name from a page title and hostname."""
    cleaned = title.strip()
    cleaned = re.sub(r"^(Welcome to|Introducing|Home\s*[-|–—·:]|Official Website\s*[-|–—·:])\s+", "", cleaned, flags=re.IGNORECASE)

    # Delimiters separating brand name from tagline
    delimiters = [" | ", " - ", " – ", " — ", " : ", " · ", ": "]
    parts = [cleaned]
    for delim in delimiters:
        if delim in parts[0]:
            parts = parts[0].split(delim)
            break

    candidate = parts[0].strip()

    # If first part is too long or a sentence, check if the last part is the brand name (e.g. "... | LangChain")
    if len(candidate) > 50 or len(candidate.split()) > 5:
        if len(parts) > 1:
            last_part = parts[-1].strip()
            if 1 <= len(last_part.split()) <= 4 and len(last_part) <= 40:
                candidate = last_part
            else:
                return None
        else:
            return None

    # Check against generic page titles
    if candidate.lower() in GENERIC_TITLES:
        if len(parts) > 1:
            second_part = parts[1].strip()
            if second_part.lower() not in GENERIC_TITLES and len(second_part.split()) <= 4:
                candidate = second_part
            else:
                return None
        else:
            return None

    # Discard if it looks like a job title, media/article, or action
    if re.search(
        r"\b(engineer|developer|architect|lead|manager|director|intern|specialist|analyst|executive|jobs|careers|schedule|agenda|news|newsletter|roundup|edition|digest|course|tutorial|podcast|conference|summit)\b",
        candidate,
        re.IGNORECASE,
    ):
        return None

    # Strip trailing corporate forms while keeping brand
    candidate = re.sub(r"\s+(Inc\.?|LLC|Ltd\.?|GmbH|Corp\.?|Corporation)$", "", candidate, flags=re.IGNORECASE).strip()

    if not candidate or len(candidate) < 2 or len(candidate) > 50:
        return None

    return candidate


def extract_hiring_signal(text: str) -> str | None:
    """Detect whether snippet or title contains public signals of active hiring."""
    text_lower = text.lower()
    hiring_keywords = [
        "we're hiring",
        "we are hiring",
        "join our team",
        "open roles",
        "open positions",
        "careers",
        "founding engineer",
        "hiring engineers",
    ]
    if any(kw in text_lower for kw in hiring_keywords):
        return "actively_hiring"
    return "not_specified"


def clean_description(snippet: str) -> str:
    """Normalize snippet text into a clean 1-2 sentence description."""
    text = snippet.strip()
    # Remove leading date stamps like "Jan 15, 2026 ... " or "April, 2026 ... "
    text = re.sub(r"^[A-Z][a-z]+(\s+\d{1,2})?,\s+202\d\s*(\.{3}|–|-|—|\.\s+)\s*", "", text)
    # Remove "Skip to content", "Sign in"
    text = re.sub(r"^(Skip to content|Sign in|Log in)\s*", "", text, flags=re.IGNORECASE)
    # Collapse whitespace
    text = re.sub(r"\s+", " ", text).strip()
    return text


def extract_company_from_result(
    result: SearchResult,
    *,
    default_industry: str | None = None,
    default_location: str | None = None,
    default_stage: str | None = None,
    target_technologies: list[str] | None = None,
) -> ExtractedCompany | None:
    """Validate and extract a structured company profile from a search result."""
    is_valid, _reason = is_valid_startup_candidate(result)
    if not is_valid:
        return None

    parsed = urlparse(str(result.url))
    hostname = (parsed.hostname or "").lower().rstrip(".")
    canonical_domain = hostname.removeprefix("www.")
    if not canonical_domain:
        return None

    company_name = extract_company_name(result.title, canonical_domain)
    if not company_name:
        return None

    # Official website URL (clean root or specific landing)
    website_url = f"{parsed.scheme}://{hostname}"

    # Extract description
    description = clean_description(result.snippet)

    # Detect hiring signal
    hiring_status = extract_hiring_signal(f"{result.title} {result.snippet}")

    # Detect technology focus
    tech_focus: list[str] = []
    if target_technologies:
        full_text = f"{result.title} {result.snippet}".lower()
        for tech in target_technologies:
            if tech.lower() in full_text and tech not in tech_focus:
                tech_focus.append(tech)

    return ExtractedCompany(
        name=company_name,
        canonical_domain=canonical_domain,
        website_url=website_url,
        description=description,
        technology_focus=tech_focus,
        industry=default_industry,
        location=default_location,
        company_stage=default_stage,
        hiring_status=hiring_status,
    )
