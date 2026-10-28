# StartupReach AI backend

## Local setup

```powershell
uv sync
uv run pytest
uv run uvicorn main:app --reload
```

The API health check is available at `GET /api/v1/health`.

## Authentication and production configuration

All API routes under `/api/v1` except the health endpoint require a bearer
token. Configure a strong random token in the backend environment:

```text
STARTUPREACH_API_TOKEN=replace-with-a-long-random-secret
ENVIRONMENT=development
CORS_ALLOWED_ORIGINS=http://localhost:5173
```

Send the token as:

```text
Authorization: Bearer replace-with-a-long-random-secret
```

The token is compared using a constant-time comparison and is never returned
or logged. The application starts without a token for local setup, but
protected requests return `503` until authentication is configured. Production
deployments must set the token through the hosting provider's secret manager.
`CORS_ALLOWED_ORIGINS` is a comma-separated allowlist; do not use `*` with
authenticated browser clients.

The API is intentionally single-user. It has no user accounts, login flow,
token rotation, roles, or multi-tenant authorization. Rotate the shared token
manually through the deployment secret configuration.

## Database configuration

Copy `.env.example` to `.env` and set `DATABASE_URL` to the Supabase PostgreSQL
connection string. The backend keeps this value server-side and normalizes
`postgres://` and `postgresql://` URLs to the SQLAlchemy `psycopg` dialect.

If the database password contains reserved URL characters such as `@`, `:`, or
`/`, URL-encode those characters in `DATABASE_URL`. For example, `@` becomes
`%40`.

Database connectivity can be checked with:

```powershell
uv run python -c "from app.db import check_database_connection; check_database_connection(); print('database connection: ok')"
```

Alembic is configured in `alembic.ini`. The Phase 2 model metadata is loaded
from `app.models`, and the initial schema revision is in
`alembic/versions/4e9d49affd79_create_phase_2_data_models.py`.

To apply the initial schema after confirming the database URL:

```powershell
uv run alembic upgrade head
```

### Database URL preflight

Before any connection or migration, run the non-networking format check:

```powershell
uv run python -m app.preflight
```

The command reports only safe fields such as the driver, whether host/database
components exist, and whether the password contains characters that should be
URL-encoded. It never prints the URL, hostname, username, password, or
credentials and does not connect to Supabase.

If a password contains reserved URL characters, percent-encode them before
putting the value in `DATABASE_URL`: `@` becomes `%40`, `:` becomes `%3A`, `/`
becomes `%2F`, `?` becomes `%3F`, `#` becomes `%23`, and `%` becomes `%25`.
Encode the password value only, preserve the URL structure, then rerun the
preflight. Supabase connectivity and `uv run alembic upgrade head` remain
manual, user-controlled staging steps.

## Discovery foundation

The provider-independent discovery layer lives in `app/discovery`. It defines
the `SearchProvider` protocol, normalized `SearchResult` records, global
`ResearchFilters`, deterministic query planning, and defensive result
normalization. A concrete provider can be added without changing these
contracts.

### Tavily provider

The first concrete provider is `TavilySearchProvider`. Configure it only on
the backend:

```text
TAVILY_API_KEY=your-tavily-api-key
TAVILY_TIMEOUT_SECONDS=15
```

Tavily credentials are loaded through the existing settings system and are
never returned to the frontend or included in logs. The key is checked when
`TavilySearchProvider.search()` is called, so the application can start
without Tavily configured. Missing credentials produce a clear configuration
error instead of fabricated results.

### Discovery orchestration

`DiscoveryService` coordinates planned queries, provider calls, and persistence
without coupling the application to Tavily. Each planned query is executed
independently so successful results can be retained when another query fails.
Normalized results are deduplicated by URL and then by canonical hostname
(lowercase, with a leading `www.` removed). Existing companies with the same
canonical domain are reused.

Each persisted result creates source evidence and a `ResearchResult` link to
the current `ResearchRun`. Company/result persistence is committed as one
transaction; database failures roll back the discovery records and mark the
run as failed. Provider failures produce a partial run with recorded error
details.

## Company research

The `app/research` package provides structured company research claims with
`verified`, `inference`, and `unknown` statuses, plus source references for
public evidence. `WebsiteResearchProvider` is a conservative public-site
adapter that extracts page title, meta description, and visible text without
claiming unsupported products, technologies, funding, hiring, or founder
information.

`CompanyResearchService` updates an existing company without replacing an
existing description with weaker evidence. Because the current Phase 2 schema
has no product/activity columns, those structured claims are retained in the
research result and their supporting evidence is persisted as
`CompanySource` records. Technology is added only from sourced verified
technical claims.

## Founder and contact research

The `app/contacts` package defines a provider-neutral
`ContactResearchProvider` and structured contact claims for founders,
co-founders, CTOs, technical co-founders, and engineering leaders. A contact
is persisted only when the provider supplies a supported public-source status
and at least one source reference. Public email, profile, and company contact
channels are stored only when explicitly supplied by that provider; the
service never derives email addresses from names or domains.

Identity and channel evidence is persisted through `ContactSource`. Existing
contacts are reused by public profile URL, email, or normalized name, and
stronger evidence can improve confidence without fabricating or replacing
unsupported fields. The current schema has no contact-category column, so the
structured category remains in the research result while the persisted
`Contact.role` and verification fields retain the operational identity data.

## Opportunity scoring

The `app/scoring` package calculates a transparent 0–100
potential-opportunity score. Default weights are:

- Technical relevance: 30
- Role relevance: 20
- Potential engineering need: 20
- Verified public activity: 15
- Verified contact accessibility: 10
- Research quality: 5

Weights must be positive and sum to 100. Each factor records its raw score,
weight, weighted contribution, evidence, explanation, and missing information.
Scores are persisted in the existing `Company.opportunity_score` and
`Company.opportunity_score_breakdown` fields. The service always labels the
result as a `potential_opportunity`; a high score never means the company is
hiring or represents a confirmed vacancy.

## Personalized email drafting

The `app/drafting` package generates concise, manual-only email drafts from
the user profile, company context, verified contacts, sourced company
research, and optional opportunity scores. Company-specific statements are
included only when backed by a source URL; otherwise the draft uses neutral
language. Drafts are persisted through the existing `EmailDraft` model with
`draft`, `ready_to_send`, and `archived` statuses.

The service supports creation, editing, and regeneration. It intentionally
does not expose a send operation, configure SMTP, or schedule outreach.

## Dashboard summary

The authenticated `GET /api/v1/dashboard/summary` endpoint returns SQL-backed
counts for companies, scores at or above 75, drafts, and research runs, plus
the five most recent companies and research runs. It avoids downloading full
paginated collections solely to render dashboard totals. Company responses
include the persisted `opportunity_score_breakdown`, while score recalculation
returns the newly calculated complete breakdown.

## Safe deployment checklist

- Set `DATABASE_URL` through a secret manager and URL-encode reserved password characters.
- Set a long random `STARTUPREACH_API_TOKEN`.
- Set an explicit production `CORS_ALLOWED_ORIGINS` allowlist.
- Set `ENVIRONMENT=production`.
- Keep `TAVILY_API_KEY` backend-only.
- Run `uv run pytest -q` before deployment.
- Run `uv run alembic heads` to inspect migration state.
- Apply migrations only after manually validating the Supabase connection string.
- Use HTTPS at the hosting layer.
- Do not expose `.env`, API keys, database URLs, or raw exception logs.
- Confirm that no email-send endpoint or outbound email integration is enabled.

The Supabase connection and initial migration remain pending manual
verification because the current local `DATABASE_URL` is malformed.

## Release hardening and staging

- Request logs are structured JSON and include request ID, method, route, status, and duration.
- Authorization headers, bearer tokens, database URLs, provider keys, request bodies, and profile content are not logged.
- Every response includes `X-Request-ID` when request processing reaches the response middleware.
- Discovery, company research, and contact research POST routes use an in-memory per-client rate limit.
- Defaults are `RATE_LIMIT_WINDOW_SECONDS=60` and `RATE_LIMIT_MAX_REQUESTS=10`.
- Rate-limited responses use the standard `rate_limited` error envelope.
- The rate limiter is process-local and resets on restart; use a reverse proxy or shared limiter before multi-instance deployment.

Manual staging checklist:

1. Configure `DATABASE_URL`, `STARTUPREACH_API_TOKEN`, `TAVILY_API_KEY`, `ENVIRONMENT=production`, and an explicit `CORS_ALLOWED_ORIGINS` allowlist in the staging secret/configuration store.
2. Run `uv run python -m app.preflight`; do not paste credentials into logs or tickets.
3. Manually validate the corrected Supabase connection from the staging environment.
4. Only after validation, manually apply `uv run alembic upgrade head`.
5. Confirm `GET /api/v1/health` through the HTTPS staging endpoint.
6. Confirm protected routes reject missing/invalid bearer tokens.
7. Check structured logs for request IDs and verify no secrets or request bodies appear.
8. Verify rate-limit responses on provider-triggering routes.
9. Set CORS to the exact staging frontend origin; do not use `*`.
10. Run backend tests before release and keep email delivery disabled.