# StartupReach AI

StartupReach AI is an intelligent discovery and outreach platform designed to identify early-stage startups, evaluate opportunity signals, and streamline founder/team outreach.

## Repository Structure

```
Startup-Reach/
├── backend/          # FastAPI REST API, SQLAlchemy ORM, Tavily discovery & scoring
└── frontend/         # React, Vite, TypeScript dashboard
```

## Quick Start

### 1. Backend Setup

```bash
cd backend
uv sync
cp .env.example .env
# Configure DATABASE_URL, TAVILY_API_KEY, and STARTUPREACH_API_TOKEN in backend/.env
uv run uvicorn main:app --reload --port 8000
```

### 2. Frontend Setup

```bash
cd frontend
npm install
cp .env.example .env
npm run dev
```

Open `http://localhost:5173` and authenticate using the bearer token configured in `STARTUPREACH_API_TOKEN`.

## Testing

- **Backend tests:** `cd backend && uv run pytest`
- **Frontend tests:** `cd frontend && npm test`
- **Frontend build:** `cd frontend && npm run build`
