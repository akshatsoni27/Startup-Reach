import re
from typing import Any
from urllib.parse import urlparse

from app.discovery.schemas import SearchResult

# High-authority job boards, ATS aggregators, recruitment agencies
BLOCKED_DOMAINS = {
    # Job boards & aggregators
    "indeed.com",
    "topgenaijobs.com",
    "dice.com",
    "builtin.com",
    "glassdoor.com",
    "ziprecruiter.com",
    "simplyhired.com",
    "levels.fyi",
    "weworkremotely.com",
    "remoteok.com",
    "hired.com",
    "wellfound.com",
    "otta.com",
    "jooble.org",
    "careerjet.com",
    "talent.com",
    "agentic-engineering-jobs.com",
    "eu-recruit.com",
    "signifytechnology.com",
    "monster.com",
    "jobvite.com",
    "greenhouse.io",
    "lever.co",
    "workable.com",
    "ashbyhq.com",
    "breezy.hr",
    "smartrecruiters.com",
    "workday.com",
    "myworkdayjobs.com",
    "remotive.com",
    "jobgether.com",
    "techcareers.com",
    "reed.co.uk",
    "totaljobs.com",
    # Corporate career portals
    "capitalonecareers.com",
    "amazon.jobs",
    "careers.google.com",
    "metacareers.com",
    # Aggregators & directories (not startups themselves)
    "topstartups.io",
    "cbinsights.com",
    "pitchbook.com",
    "crunchbase.com",
    "startupintros.com",
    "ycombinator.com",
    # News, media, blogs, listicles & content platforms
    "medium.com",
    "substack.com",
    "dev.to",
    "youtube.com",
    "youtu.be",
    "coursera.org",
    "udemy.com",
    "edx.org",
    "wikipedia.org",
    "facebook.com",
    "twitter.com",
    "x.com",
    "instagram.com",
    "reddit.com",
    "tiktok.com",
    "yahoo.com",
    "finance.yahoo.com",
    "businessinsider.com",
    "bloomberg.com",
    "techcrunch.com",
    "forbes.com",
    "reuters.com",
    "cnbc.com",
    "nytimes.com",
    "wsj.com",
    "theinformation.com",
    "wired.com",
    "venturebeat.com",
    "eu-startups.com",
    "newmarketpitch.com",
    "neurons-lab.com",
    "arize.com",
    # Conference & events
    "ai.engineer",
    "eventbrite.com",
    "meetup.com",
    "luma.com",
    "lu.ma",
    # Large established corporations (not early-stage startups)
    "capitalone.com",
    "microsoft.com",
    "google.com",
    "apple.com",
    "amazon.com",
    "meta.com",
    "ibm.com",
    "oracle.com",
    "cisco.com",
    "walmart.com",
    "jpmorgan.com",
    "goldmansachs.com",
    "accenture.com",
    "deloitte.com",
}

BLOCKED_HOST_SUBSTRINGS = (
    "-jobs",
    "jobboard",
    "careers.",
    "jobs.",
    "recruit",
    "talent.",
    "apply.",
    "blog.",
    "news.",
    "newsletter.",
)

BLOCKED_PATH_PATTERNS = [
    re.compile(r"^/(job|jobs|careers|career|openings|viewjob|posting|postings|vacancy|vacancies)/?", re.IGNORECASE),
    re.compile(r"^/(schedule|agenda|speakers|tickets|registration|event|events)/?", re.IGNORECASE),
    re.compile(r"^/(watch|video|courses|tutorial|posts|status|stories)/?", re.IGNORECASE),
    re.compile(r"^/(article|articles|news|blog|category|tag|posts|podcasts)/?", re.IGNORECASE),
]

JOB_TITLE_PATTERNS = [
    # Explicit job board title indicators
    re.compile(r"\b(jobs?|employment|vacanc(y|ies)|hiring)\s*([·|–—\-:]|\bat\b)", re.IGNORECASE),
    # Common job title formulas: "Role at Company"
    re.compile(
        r"\b(full\s*stack|backend|frontend|software|ai|machine\s*learning|data|devops|cloud|systems|sales|account\s*executive|technology\s*lead)\s+(engineer|developer|architect|lead|manager|director|intern|specialist)\b.*(\bat\b|\bwith\b|\bin\b|[·|–—\-])",
        re.IGNORECASE,
    ),
    re.compile(r"\b(engineer|developer|lead)\s+\d+\b", re.IGNORECASE),  # e.g., Engineer 4
    re.compile(r"\bat\s+(capital\s*one|amazon|google|microsoft|apple|meta|ibm|oracle|walmart|jpmorgan)\b", re.IGNORECASE),
]

EVENT_PATTERNS = [
    re.compile(r"^(schedule|agenda|speakers|tickets|venue)\s*[|·–—\-:]", re.IGNORECASE),
    re.compile(r"\bconferences?\s+in\s+\d{4}\b", re.IGNORECASE),
    re.compile(r"\b(summit|symposium|expo|hackathon)\b.*(202\d|schedule|agenda)", re.IGNORECASE),
]

COURSE_PATTERNS = [
    re.compile(r"\b(full\s*course|masterclass|tutorial|bootcamp|lecture|syllabus|certification)\b", re.IGNORECASE),
]

LISTICLE_PATTERNS = [
    re.compile(r"^(top\s+\d+|\d+\s+best|\d+\s+top|list\s+of)\b", re.IGNORECASE),
    re.compile(r"\b(\d+\s+listings\s+ranked|\d+\s+startups\s+to\s+watch|\d+\s+companies\s+in\s+202\d)\b", re.IGNORECASE),
    re.compile(r"^\d+\s+top\s+[a-z\s]+(cities|companies|startups)\b", re.IGNORECASE),
    re.compile(r"\b(launches\s+news|product\s+launches|startup\s+edition|monthly\s+roundup|weekly\s+roundup|newsletter|digest)\b", re.IGNORECASE),
    re.compile(r"\b(raises\s+[\$£€\d]|funding\s+round|series\s+[a-e]|hits\s+[\$£€\d].*valuation)\b", re.IGNORECASE),
]

GENERIC_TITLES = {
    "home",
    "home page",
    "homepage",
    "about",
    "about us",
    "careers",
    "jobs",
    "job openings",
    "schedule",
    "agenda",
    "events",
    "blog",
    "news",
    "contact",
    "contact us",
    "login",
    "sign in",
    "signup",
    "privacy policy",
    "terms of service",
    "pricing",
}


def is_valid_startup_candidate(result: SearchResult) -> tuple[bool, str | None]:
    """Inspect URL, domain, title, and snippet to verify if result represents a valid startup candidate."""
    url_str = str(result.url)
    parsed = urlparse(url_str)
    hostname = (parsed.hostname or "").lower().rstrip(".")
    clean_host = hostname.removeprefix("www.")
    path = parsed.path or "/"
    title = (result.title or "").strip()
    snippet = (result.snippet or "").strip()

    # 1. Inspect domain and subdomains
    if clean_host in BLOCKED_DOMAINS:
        return False, f"blocked_domain:{clean_host}"
    for blocked in BLOCKED_DOMAINS:
        if clean_host.endswith("." + blocked):
            return False, f"blocked_parent_domain:{blocked}"

    for substr in BLOCKED_HOST_SUBSTRINGS:
        if substr in clean_host:
            return False, f"blocked_host_pattern:{substr}"

    # 2. Inspect URL path
    for pattern in BLOCKED_PATH_PATTERNS:
        if pattern.search(path):
            return False, f"blocked_path_pattern:{pattern.pattern}"

    # 3. Inspect title patterns
    for pattern in JOB_TITLE_PATTERNS:
        if pattern.search(title):
            return False, f"job_listing_title:{title}"

    for pattern in EVENT_PATTERNS:
        if pattern.search(title):
            return False, f"event_schedule_title:{title}"

    for pattern in COURSE_PATTERNS:
        if pattern.search(title):
            return False, f"course_tutorial_title:{title}"

    for pattern in LISTICLE_PATTERNS:
        if pattern.search(title):
            return False, f"listicle_or_aggregator_title:{title}"

    # 4. Check snippet for pure job aggregations or events
    snippet_lower = snippet.lower()
    if any(
        phrase in snippet_lower
        for phrase in [
            "search 100+ jobs",
            "search thousands of jobs",
            "conference schedule",
            "view all sessions and speakers",
            "apply now for the position of",
            "job description and requirements",
        ]
    ):
        return False, "aggregator_or_job_snippet"

    return True, None
