export type Page<T> = { items: T[]; page: number; page_size: number; total: number };

export type Company = {
  id: string; name: string; canonical_domain: string | null; website_url: string | null;
  description: string | null; industry: string | null; technology_focus: string[];
  location: string | null; country: string | null; company_stage: string | null;
  hiring_status: string | null; opportunity_status: string; opportunity_score: number | null;
  opportunity_score_breakdown: { factors?: ScoreFactor[]; explanation?: string; missing_information?: string[]; weights_total?: number };
  research_status: string; last_researched_at: string | null;
};
export type Source = { id: string; source_type: string; source_url: string; title: string | null; evidence_text: string | null };
export type Contact = { id: string; company_id: string; name: string; role: string | null; email: string | null; email_verification_status: string | null; professional_profile_url: string | null; company_contact_url: string | null; confidence_score: number | null; research_status: string };
export type ResearchRun = { id: string; query: string; status: string; total_results: number; unique_companies_found: number; errors: Record<string, unknown>[] };
export type DraftStatus = "draft" | "ready_to_send" | "archived";
export type Evidence = { claim: string; source_url: string | null };
export type Draft = { id: string; company_id: string; contact_id: string | null; subject: { text: string }; body: { text: string }; recipient_name: string | null; recipient_role: string | null; personalization_evidence: Evidence[]; status: DraftStatus; manual_only: boolean; metadata: Record<string, unknown> | null };
export type ScoreFactor = { name: string; score: number; weight: number; weighted_score: number; evidence: { source_url: string; evidence: string }[]; explanation: string; missing_information: string[] };
export type OpportunityScore = { company_id: string; score: number; label: string; opportunity_status: string; breakdown: { factors: ScoreFactor[]; weights_total: number; explanation: string; missing_information: string[] }; factors: ScoreFactor[] };
export type Profile = { name: string; email: string; portfolio_url: string | null; resume_text: string | null; skills: string[]; experience: Record<string, unknown>[]; projects: Record<string, unknown>[]; preferred_roles: string[]; preferred_locations: string[]; preferred_industries: string[] };
export type DashboardSummary = { company_count: number; high_potential_company_count: number; draft_count: number; research_run_count: number; recent_companies: Company[]; recent_research_runs: ResearchRun[] };
