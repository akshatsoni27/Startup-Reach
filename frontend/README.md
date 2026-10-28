# StartupReach AI dashboard

## Local setup

1. Start the backend from `backend/`:

   ```powershell
   uv run uvicorn main:app --reload
   ```

2. From this directory, install dependencies and start Vite:

   ```powershell
   npm install
   Copy-Item .env.example .env
   npm run dev
   ```

3. Open the Vite URL (normally `http://localhost:5173`). Enter the value of
   the backend's `STARTUPREACH_API_TOKEN` in the workspace access field.

`VITE_API_BASE_URL` is the only frontend environment value. It contains the
backend URL and is not a secret. Do not put the bearer token, Tavily key, or
database URL in a `VITE_` variable: Vite exposes those values to browser code.
The shared token is entered by the user and kept in `sessionStorage` only.

## Available views

- Overview: saved companies, recent runs, matches, and draft counts.
- Discover startups: global discovery filters and run results.
- Companies: paginated company library and evidence-backed company detail.
- Email drafts: manual-only draft editing, regeneration, evidence, and status.
- Profile & settings: create or update the single user's skills, experience,
  role preferences, location preferences, and industry goals.

The frontend never sends email and has no SMTP or provider credential
integration. A high score is labelled as a potential opportunity, not a
confirmed vacancy.

The dashboard uses `GET /api/v1/dashboard/summary` for SQL-backed counts and
small recent-item lists instead of downloading complete company or draft
collections. Persisted company responses include the existing score breakdown;
the score action returns the complete newly calculated breakdown.

## Tests

```powershell
npm test
npm run build
npm run test:e2e
```

The current backend is intentionally single-user. Authentication is a shared
bearer token with no accounts, roles, refresh tokens, or multi-user isolation.

## Staging readiness

Configure only `VITE_API_BASE_URL` in the frontend build environment. Never put
`STARTUPREACH_API_TOKEN`, `TAVILY_API_KEY`, `DATABASE_URL`, or any other secret
in a `VITE_` variable because Vite embeds those values into browser assets.
The shared bearer token is entered by the operator and kept in
`sessionStorage`.

Before staging:

1. Serve the frontend and backend over HTTPS.
2. Set `VITE_API_BASE_URL` to the HTTPS staging API origin.
3. Configure the backend CORS allowlist to the exact staging frontend origin.
4. Configure the shared backend token through the staging secret manager.
5. Confirm `GET /api/v1/health` and a protected request.
6. Confirm no email-send action exists; drafts remain manual-only.
7. Run `npm test`, `npm run build`, and `npm run test:e2e`.

The current npm audit reports three development-only advisories: two critical
issues in `tinypool` and one moderate issue in Vitest's mocker dependency.
They are pulled in by Vitest and do not ship in the production bundle. The
available automated fix requires Vitest 5, a major upgrade, so no forced or
breaking remediation was applied in this phase. Review and upgrade the test
toolchain in a separate dependency-maintenance change.

The Playwright suite uses mocked API responses and does not contact Supabase,
Tavily, or any live provider. Install a browser once with
`npx playwright install chromium` before running it locally.

`npm audit` currently reports three dependency-tree vulnerabilities (one
moderate and two critical) after the frontend dependency installation. No
forced upgrade was applied because it may introduce breaking changes. Review
the advisories and upgrade the affected packages in a dedicated dependency
maintenance change.
