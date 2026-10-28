import type { Company, Contact, DashboardSummary, Draft, DraftStatus, OpportunityScore, Page, Profile, ResearchRun, Source } from "./types";

const baseUrl = (import.meta.env.VITE_API_BASE_URL || "http://localhost:8000").replace(/\/$/, "");
const tokenKey = "startupreach_api_token";

export class ApiError extends Error {
  constructor(public status: number, public code: string, message: string) { super(message); }
}
export const auth = {
  get: () => sessionStorage.getItem(tokenKey) || "",
  set: (token: string) => sessionStorage.setItem(tokenKey, token),
  clear: () => sessionStorage.removeItem(tokenKey),
};

async function request<T>(path: string, init: RequestInit = {}): Promise<T> {
  const headers = new Headers(init.headers);
  headers.set("Content-Type", "application/json");
  const token = auth.get();
  if (token) headers.set("Authorization", `Bearer ${token}`);
  let response: Response;
  try {
    response = await fetch(`${baseUrl}${path}`, { ...init, headers });
  } catch (error) {
    if (error instanceof ApiError) throw error;
    throw new ApiError(0, "network_error", "Unable to connect to the API server. Please check your backend connection.");
  }
  if (!response.ok) {
    const body = await response.json().catch(() => ({})) as { code?: string; message?: string };
    if (response.status === 401) auth.clear();
    throw new ApiError(response.status, body.code || "request_error", body.message || "The request could not be completed.");
  }
  if (response.status === 204) return undefined as T;
  return response.json() as Promise<T>;
}
const json = (body: unknown): RequestInit => ({ method: "POST", body: JSON.stringify(body) });

export const api = {
  profile: () => request<Profile>("/api/v1/profile"),
  createProfile: (profile: Profile) => request<Profile>("/api/v1/profile", { method: "POST", body: JSON.stringify({ ...profile, portfolio_url: profile.portfolio_url || null }) }),
  updateProfile: (profile: Profile) => request<Profile>("/api/v1/profile", { method: "PUT", body: JSON.stringify({ ...profile, portfolio_url: profile.portfolio_url || null }) }),
  dashboard: () => request<DashboardSummary>("/api/v1/dashboard/summary"),
  companies: (page = 1) => request<Page<Company>>(`/api/v1/companies?page=${page}&page_size=20`),
  company: (id: string) => request<Company>(`/api/v1/companies/${id}`),
  sources: (id: string) => request<Source[]>(`/api/v1/companies/${id}/sources`),
  contacts: (id: string) => request<Contact[]>(`/api/v1/companies/${id}/contacts`),
  runs: () => request<ResearchRun[]>("/api/v1/research-runs"),
  discover: (filters: Record<string, unknown>) => request<ResearchRun>("/api/v1/research-runs", json(filters)),
  researchCompany: (id: string) => request<Record<string, unknown>>(`/api/v1/companies/${id}/research`, json({})),
  researchContacts: (id: string) => request<Record<string, unknown>>(`/api/v1/companies/${id}/contacts/research`, json({})),
  score: async (id: string) => { const result = await request<OpportunityScore>(`/api/v1/companies/${id}/score`, json({})); return { ...result, factors: result.breakdown.factors }; },
  drafts: (page = 1) => request<Page<Draft>>(`/api/v1/drafts?page=${page}&page_size=20`),
  draft: (id: string) => request<Draft>(`/api/v1/drafts/${id}`),
  createDraft: (companyId: string, contactId?: string) => request<Draft>(`/api/v1/companies/${companyId}/drafts`, json({ company_id: companyId, contact_id: contactId || null })),
  editDraft: (id: string, body: { subject?: string; body?: string; status?: DraftStatus }) => request<Draft>(`/api/v1/drafts/${id}`, { method: "PUT", body: JSON.stringify(body) }),
  regenerateDraft: (id: string) => request<Draft>(`/api/v1/drafts/${id}/regenerate`, json({})),
  status: (id: string, status: DraftStatus) => request<Draft>(`/api/v1/drafts/${id}/status`, json({ status })),
};
