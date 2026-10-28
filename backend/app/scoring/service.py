from dataclasses import dataclass
from typing import Iterable

from sqlalchemy.orm import Session

from app.contacts.schemas import ContactVerificationStatus
from app.models import Company, UserProfile
from app.research.schemas import ClaimStatus, CompanyResearch
from app.scoring.schemas import (
    EvidenceReference,
    OpportunityScore,
    ScoreBreakdown,
    ScoringFactor,
)


@dataclass(frozen=True)
class ScoringWeights:
    technical_relevance: float = 30
    role_relevance: float = 20
    engineering_need: float = 20
    activity_signals: float = 15
    contact_accessibility: float = 10
    research_quality: float = 5

    def __post_init__(self) -> None:
        weights = self.as_dict()
        if any(value <= 0 for value in weights.values()):
            raise ValueError("scoring weights must be positive")
        if abs(sum(weights.values()) - 100) > 0.001:
            raise ValueError("scoring weights must sum to 100")

    def as_dict(self) -> dict[str, float]:
        return {
            "technical_relevance": self.technical_relevance,
            "role_relevance": self.role_relevance,
            "engineering_need": self.engineering_need,
            "activity_signals": self.activity_signals,
            "contact_accessibility": self.contact_accessibility,
            "research_quality": self.research_quality,
        }


class OpportunityScoringService:
    """Calculates an evidence-backed potential-opportunity score."""

    def __init__(
        self,
        session: Session | None = None,
        *,
        weights: ScoringWeights | None = None,
    ) -> None:
        self._session = session
        self._weights = weights or ScoringWeights()

    def score(
        self,
        company: Company,
        profile: UserProfile,
        *,
        research: CompanyResearch | None = None,
    ) -> OpportunityScore:
        factors = [
            self._technical_factor(company, profile, research),
            self._role_factor(company, profile),
            self._engineering_need_factor(company),
            self._activity_factor(research),
            self._contact_factor(company),
            self._research_quality_factor(company, research),
        ]
        weights_total = sum(factor.weight for factor in factors)
        total = round(sum(factor.weighted_score for factor in factors))
        breakdown = ScoreBreakdown(
            factors=factors,
            weights_total=weights_total,
            explanation=self._overall_explanation(total, factors),
            missing_information=list(
                dict.fromkeys(
                    missing
                    for factor in factors
                    for missing in factor.missing_information
                )
            ),
        )
        result = OpportunityScore(
            company_id=company.id,
            score=max(0, min(100, total)),
            label=self._label(total),
            opportunity_status="potential_opportunity",
            breakdown=breakdown,
            metadata={"confirmed_vacancy": False},
        )
        if self._session is not None:
            company.opportunity_score = result.score
            company.opportunity_score_breakdown = result.breakdown.model_dump(mode="json")
            company.opportunity_status = result.opportunity_status
            self._session.commit()
        return result

    def _technical_factor(
        self,
        company: Company,
        profile: UserProfile,
        research: CompanyResearch | None,
    ) -> ScoringFactor:
        user_terms = _terms(
            [*profile.skills, *_json_texts(profile.projects), *_json_texts(profile.experience)]
        )
        company_terms = _terms(company.technology_focus)
        matches = sorted(user_terms & company_terms)
        evidence = [
            EvidenceReference(
                source_url=str(source.source_url),
                evidence=source.evidence_text or "Company technology evidence",
            )
            for source in company.sources
            if any(match in _terms([source.evidence_text or ""]) for match in matches)
        ]
        if research:
            for claim in research.technical_context:
                if claim.status == ClaimStatus.VERIFIED:
                    evidence.extend(
                        EvidenceReference(source_url=str(url), evidence=claim.claim)
                        for url in claim.source_urls
                    )
        score = min(100, len(matches) * 25)
        missing = [] if matches else ["No overlapping user skills and company technologies."]
        return self._factor(
            "technical_relevance",
            score,
            self._weights.technical_relevance,
            f"{len(matches)} supported technical skill match(es).",
            evidence,
            missing,
        )

    def _role_factor(self, company: Company, profile: UserProfile) -> ScoringFactor:
        roles = _terms(profile.preferred_roles)
        searchable = _terms([company.description or "", company.industry or ""])
        matches = sorted(role for role in roles if role in searchable)
        score = 100 if matches else 0
        return self._factor(
            "role_relevance",
            score,
            self._weights.role_relevance,
            "Target role language is supported by company description or industry."
            if matches
            else "No target-role evidence was found in the company record.",
            [],
            [] if matches else ["Company role context is missing or does not match target roles."],
        )

    def _engineering_need_factor(self, company: Company) -> ScoringFactor:
        stage_terms = _terms([company.company_stage or ""])
        need_terms = _terms([company.description or "", company.industry or ""])
        stage_score = 60 if stage_terms & {"seed", "early", "startup"} else 0
        need_score = 40 if need_terms & {"software", "technology", "ai", "saas"} else 0
        score = min(100, stage_score + need_score)
        return self._factor(
            "engineering_need",
            score,
            self._weights.engineering_need,
            "Potential engineering need is inferred from public company context; this is not a hiring claim.",
            [],
            [] if score else ["Company stage or engineering context is unknown."],
        )

    def _activity_factor(self, research: CompanyResearch | None) -> ScoringFactor:
        claims = [
            claim for claim in (research.activity_signals if research else [])
            if claim.status == ClaimStatus.VERIFIED and claim.source_urls
        ]
        evidence = [
            EvidenceReference(source_url=str(url), evidence=claim.claim)
            for claim in claims
            for url in claim.source_urls
        ]
        score = min(100, len(claims) * 50)
        return self._factor(
            "activity_signals",
            score,
            self._weights.activity_signals,
            f"{len(claims)} verified public activity signal(s).",
            evidence,
            [] if claims else ["No verified public activity signals were provided."],
        )

    def _contact_factor(self, company: Company) -> ScoringFactor:
        supported = [
            contact
            for contact in company.contacts
            if contact.email_verification_status
            in {
                ContactVerificationStatus.VERIFIED_OFFICIAL_SOURCE.value,
                ContactVerificationStatus.SUPPORTED_PUBLIC_SOURCE.value,
            }
        ]
        score = 100 if supported else 0
        return self._factor(
            "contact_accessibility",
            score,
            self._weights.contact_accessibility,
            "A publicly supported decision-maker contact is available."
            if supported
            else "No verified founder or technical contact is available.",
            [],
            [] if supported else ["Verified founder or technical contact is missing."],
        )

    def _research_quality_factor(
        self, company: Company, research: CompanyResearch | None
    ) -> ScoringFactor:
        score = 0
        evidence: list[EvidenceReference] = []
        if company.description:
            score += 40
        if company.sources:
            score += 30
            evidence.extend(
                EvidenceReference(source_url=source.source_url, evidence=source.evidence_text or "")
                for source in company.sources
                if source.evidence_text
            )
        if research and research.status.value == "completed":
            score += 30
        return self._factor(
            "research_quality",
            score,
            self._weights.research_quality,
            "Research completeness is based only on populated, sourced fields.",
            evidence,
            [] if score == 100 else ["Company research is incomplete."],
        )

    def _factor(
        self,
        name: str,
        score: float,
        weight: float,
        explanation: str,
        evidence: list[EvidenceReference],
        missing: list[str],
    ) -> ScoringFactor:
        return ScoringFactor(
            name=name,
            score=score,
            weight=weight,
            weighted_score=score * weight / 100,
            explanation=explanation,
            evidence=evidence,
            missing_information=missing,
        )

    @staticmethod
    def _label(score: int) -> str:
        if score >= 70:
            return "High potential match"
        if score >= 40:
            return "Good potential match"
        return "Needs further research"

    @staticmethod
    def _overall_explanation(score: int, factors: Iterable[ScoringFactor]) -> str:
        strongest = max(factors, key=lambda factor: factor.weighted_score)
        return (
            f"Score {score}/100 is a potential-opportunity assessment, not a confirmed vacancy. "
            f"The strongest factor was {strongest.name}."
        )


def _terms(values: Iterable[str]) -> set[str]:
    return {
        term.strip(".,:;()[]{}").casefold()
        for value in values
        for term in value.split()
        if term.strip(".,:;()[]{}")
    }


def _json_texts(values: list[dict[str, object]]) -> list[str]:
    return [str(value) for item in values for value in item.values()]
