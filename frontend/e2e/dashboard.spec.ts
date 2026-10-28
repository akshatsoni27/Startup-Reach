import { expect, test } from "@playwright/test";

const company = {
  id: "11111111-1111-1111-1111-111111111111",
  name: "Northstar Labs",
  canonical_domain: "northstar.example",
  website_url: "https://northstar.example",
  description: "Developer tools for distributed teams.",
  industry: "Developer tools",
  technology_focus: ["Python"],
  location: "Remote",
  country: "Global",
  company_stage: "Seed",
  hiring_status: null,
  opportunity_status: "potential_opportunity",
  opportunity_score: 82,
  opportunity_score_breakdown: { factors: [], weights_total: 100 },
  research_status: "researched",
  last_researched_at: null,
};
const draft = {
  id: "22222222-2222-2222-2222-222222222222",
  company_id: company.id,
  contact_id: null,
  subject: { text: "Exploring engineering opportunities" },
  body: { text: "Hello Northstar team," },
  recipient_name: null,
  recipient_role: null,
  personalization_evidence: [],
  status: "draft",
  manual_only: true,
  metadata: null,
};

test.beforeEach(async ({ page }) => {
  await page.route("**/api/v1/**", async route => {
    const url = new URL(route.request().url());
    if (url.pathname.endsWith("/dashboard/summary")) {
      return route.fulfill({ json: { company_count: 1, high_potential_company_count: 1, draft_count: 0, research_run_count: 0, recent_companies: [company], recent_research_runs: [] } });
    }
    if (url.pathname.endsWith("/companies") && route.request().method() === "GET") {
      return route.fulfill({ json: { items: [company], page: 1, page_size: 20, total: 1 } });
    }
    if (url.pathname.includes("/sources")) return route.fulfill({ json: [] });
    if (url.pathname.includes("/contacts")) return route.fulfill({ json: [] });
    if (url.pathname.endsWith("/companies/11111111-1111-1111-1111-111111111111")) {
      return route.fulfill({ json: company });
    }
    if (url.pathname.endsWith("/research-runs")) return route.fulfill({ json: [] });
    if (url.pathname.endsWith("/profile")) return route.fulfill({ status: 404, json: { code: "not_found", message: "User profile not found." } });
    if (url.pathname.endsWith("/drafts") && route.request().method() === "GET") return route.fulfill({ json: { items: [], page: 1, page_size: 20, total: 0 } });
    if (url.pathname.endsWith("/research") && route.request().method() === "POST") return route.fulfill({ json: { status: "completed", errors: [] } });
    if (url.pathname.endsWith("/score") && route.request().method() === "POST") return route.fulfill({ json: { company_id: company.id, score: 82, label: "promising", opportunity_status: "potential_opportunity", breakdown: { factors: [], weights_total: 100, explanation: "Evidence-backed potential.", missing_information: [] } } });
    if (url.pathname.endsWith("/drafts") && route.request().method() === "POST") return route.fulfill({ status: 201, json: draft });
    if (url.pathname.endsWith("/drafts/22222222-2222-2222-2222-222222222222")) return route.fulfill({ json: draft });
    return route.fulfill({ json: {} });
  });
});

test("authenticates, discovers, reviews a company, and handles empty drafts", async ({ page }) => {
  await page.goto("/");
  await page.getByLabel("API bearer token").fill("test-token");
  await page.getByRole("button", { name: "Save API token" }).click();
  await expect(page.getByText("Saved companies")).toBeVisible();
  await page.getByRole("link", { name: "Discover startups" }).click();
  await expect(page.getByRole("heading", { name: "Find the next company to learn from." })).toBeVisible();
  await page.getByRole("button", { name: "Run discovery" }).click();
  await page.goto("/companies");
  await page.getByRole("link", { name: "Northstar Labs" }).click();
  await expect(page.locator("h1", { hasText: "Northstar Labs" })).toBeVisible();
  await expect(page.getByText("A promising lead is not a confirmed job vacancy.")).toBeVisible();
  await page.getByRole("button", { name: "Research company" }).click();
  await expect(page.getByText("Research completed.")).toBeVisible();
  await page.getByRole("button", { name: "Recalculate score" }).click();
  await expect(page.getByText("Opportunity score updated.")).toBeVisible();
  await page.getByRole("button", { name: "Create draft" }).click();
  await expect(page.getByRole("heading", { name: "Personalized outreach" })).toBeVisible();
  await page.getByLabel("Subject").fill("A revised subject");
  await page.getByLabel("Body").fill("A revised body");
  await page.getByRole("button", { name: "Save changes" }).click();
  await expect(page.getByText("Draft saved.")).toBeVisible();
  await page.getByRole("link", { name: "Email drafts", exact: true }).click();
  await expect(page.getByRole("heading", { name: "Email drafts" })).toBeVisible();
});
