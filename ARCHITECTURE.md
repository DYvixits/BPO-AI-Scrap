# Architecture

## 1. Service diagram

```
                        ┌─────────────┐
                        │   Frontend   │  Vite + React + TS
                        │ (SPA, port  │  TanStack Query, Zustand,
                        │   5173)     │  React Router, React Flow*
                        └──────┬──────┘
                               │ HTTPS / WSS
                               ▼
                        ┌─────────────┐
                        │   FastAPI    │  API-only. Never runs long
                        │  (port 8000)│  tasks itself — enqueues them.
                        └──────┬──────┘
                     ┌─────────┼─────────┐
                     ▼         ▼         ▼
              ┌───────────┐ ┌─────┐ ┌──────────┐
              │ PostgreSQL │ │Redis │ │  Redis   │
              │ (system of │ │queue │ │ pub/sub  │
              │  record)   │ │(arq) │ │(live UI) │
              └───────────┘ └──┬───┘ └────▲─────┘
                                │          │
                                ▼          │
                         ┌─────────────┐   │
                         │   Worker    │───┘  publishes progress events
                         │ (arq pool)  │      consumed by FastAPI's
                         └──────┬──────┘      WebSocket endpoint
                                │
                 ┌──────────────┼──────────────┐
                 ▼              ▼              ▼
          ┌────────────┐ ┌────────────┐ ┌────────────┐
          │  Search    │ │  Crawler   │ │ Extraction │
          │  Engine    │ │  Engine    │ │  Engine    │
          │(provider   │ │(httpx, SSRF│ │(trafilatura│
          │ abstraction│ │ guarded)   │ │ + bs4/lxml)│
          └────────────┘ └────────────┘ └────────────┘
```

`*` React Flow (research map / workflow designer) ships in Phase 7/Phase 15
of the UI plan — not part of the Phase 1–3 slice.

Future services (added in later phases, see phase plan): Playwright browser
worker pool, OpenSearch (full-text), Qdrant (vector/semantic search), Neo4j
(knowledge graph), MinIO (document/snapshot storage), Prometheus + Grafana +
OpenTelemetry (observability), a dedicated MCP server process.

## 2. Why arq (Redis), not RabbitMQ/Celery, for Phase 1–3

The spec allows "RabbitMQ ou équivalent." FastAPI's core constraint is async
I/O throughout; Celery is a sync-first framework bolted onto async code with
friction, and running RabbitMQ + Celery + Redis simultaneously is three moving
parts for an MVP that needs one queue. **arq** is a small async-native task
queue built on Redis: same broker as the cache/pub-mechanism we already need,
worker code is `async def`, and it integrates cleanly with SQLAlchemy's async
engine. This is a **provider-abstracted** choice — the task-dispatch boundary
(`app/services/research_orchestrator.py`) does not leak arq-specific types
into callers, so swapping in RabbitMQ/Celery or Kafka later (Phase 11,
horizontal scale) is a contained change, not a rewrite.

## 3. Repository layout

```
bpo-ai-scrap/
├── README.md
├── ARCHITECTURE.md
├── SECURITY.md
├── docs/
│   ├── API.md
│   └── phases/PHASE_PLAN.md
├── docker-compose.yml
├── .env.example
├── backend/
│   ├── pyproject.toml
│   ├── alembic.ini
│   ├── Dockerfile
│   ├── app/
│   │   ├── main.py                 # FastAPI app factory
│   │   ├── core/                   # config, db session, redis, security, logging
│   │   ├── models/                 # SQLAlchemy 2 ORM models
│   │   ├── schemas/                # Pydantic v2 request/response contracts
│   │   ├── repositories/           # DB access, one per aggregate
│   │   ├── services/               # orchestration / business logic
│   │   ├── engines/
│   │   │   ├── search/             # SearchProvider abstraction + DuckDuckGo impl
│   │   │   ├── crawler/            # HTTP crawler + SSRF guard
│   │   │   └── extraction/         # trafilatura/bs4-based content extraction
│   │   ├── workers/
│   │   │   ├── worker.py           # arq WorkerSettings
│   │   │   └── tasks/research.py   # the research pipeline job
│   │   ├── api/v1/                 # FastAPI routers
│   │   └── integrations/           # external provider clients (future)
│   ├── migrations/                 # Alembic
│   └── tests/
├── frontend/
│   ├── package.json / vite.config.ts / tailwind.config.ts
│   └── src/
│       ├── app/                    # router, providers, query client
│       ├── components/ui/          # design-system primitives (button, card, ...)
│       ├── features/{auth,research,dashboard}/
│       ├── pages/
│       ├── stores/                 # Zustand
│       ├── services/               # API client
│       ├── types/
│       └── layouts/
└── .github/workflows/ci.yml
```

## 4. Data model (Phase 1–3 slice)

Full target schema is listed in the phase plan (§ "Database — target state");
what exists now:

```
organizations
  id (uuid pk), name, slug, tier (enum: standard|pro|business|enterprise), created_at

tenant_quotas
  id (uuid pk), organization_id fk (unique), crawl_concurrency,
  max_concurrent_research_jobs, ai_budget_cents, storage_mb_limit,
  worker_priority, created_at
  # seeded from tier defaults at signup, then an ordinary editable row
  # (Configuration Engine pattern) — see app/services/tenant_quotas.py

users
  id (uuid pk), email (unique), hashed_password, full_name,
  is_active, is_superuser, created_at

organization_members
  id (uuid pk), organization_id fk, user_id fk, role (enum RBAC), created_at
  # roles: super_admin, admin, research_manager, researcher, analyst, viewer, api_client

research_jobs
  id (uuid pk), organization_id fk, created_by fk(user),
  query (text, the natural-language request), status (enum state machine),
  mode (enum: quick|balanced|deep|verified|investigation|custom),
  config (jsonb — depth, max_pages, min_sources, ...),
  created_at, started_at, completed_at, error

research_events
  id (uuid pk), organization_id fk, research_job_id fk, kind (text),
  payload (jsonb), created_at
  # append-only log; also published on Redis pub/sub for live UI

sources
  id (uuid pk), organization_id fk, research_job_id fk, url, domain,
  status, discovered_at

crawl_pages
  id (uuid pk), organization_id fk, source_id fk, url, http_status,
  content_hash, title, extracted_text, extracted_at, error

research_results
  id (uuid pk), organization_id fk, research_job_id fk, crawl_page_id fk (nullable),
  title, url, snippet, confidence (float, currently source/freshness-based —
  see PHASE_PLAN §6 for the full multi-source Truth Engine), created_at
```

All tables use UUID primary keys and are scoped by `organization_id` for
tenant isolation. `organization_id` is denormalized directly onto
`research_events`/`sources`/`crawl_pages`/`research_results` (rather than
living only on `research_jobs` and requiring a join) for two reasons: it
keeps app-layer filters and indexes simple, and it's what makes PostgreSQL
Row-Level Security on those four tables a plain equality check instead of a
subquery — see SECURITY.md §"Tenant isolation" for the full RLS design,
including why `research_jobs` itself is deliberately excluded from RLS.

`research_jobs.status` state machine (subset of the full 71-state spec target):

```
CREATED → QUEUED → SEARCHING → CRAWLING → EXTRACTING → COMPLETED
                                                       ↘ FAILED
```

## 5. API contract (Phase 1–3)

Full OpenAPI is generated at `/docs` and `/openapi.json` when the app runs.
Summary (see `docs/API.md` for request/response shapes):

```
POST   /api/v1/auth/register
POST   /api/v1/auth/login          → {access_token, refresh_token}
POST   /api/v1/auth/refresh
GET    /api/v1/auth/me

POST   /api/v1/research            → create + enqueue a research job
GET    /api/v1/research            → list jobs for caller's org
GET    /api/v1/research/{id}       → job detail + status
GET    /api/v1/research/{id}/results
WS     /api/v1/research/{id}/ws    → live progress events

GET    /api/v1/health              → liveness/readiness (checks DB + Redis)
```

Every research/auth route requires a JWT bearer token except register/login;
every research route additionally enforces organization scoping from the
token's claims — a user can never read another organization's job.

## 6. Security posture (Phase 1–3; full list in SECURITY.md)

- Passwords hashed with bcrypt (passlib); JWT access + refresh tokens (HS256,
  short-lived access token, longer-lived refresh token, both revocable by
  rotating the signing secret in an emergency).
- **SSRF guard on every crawl**: the crawler resolves the URL's host and
  rejects loopback, link-local, private (RFC1918), multicast, and
  reserved ranges before issuing any request, and re-checks on every
  redirect hop (protects against DNS-rebinding). Only `http`/`https` schemes
  are allowed.
- Web content is **untrusted data**, never treated as instructions — the
  extraction pipeline never feeds raw crawled HTML/text into anything that
  interprets it as commands (no AI agent loop reads page content as tool
  input in this phase; that boundary is documented ahead of Phase 8 AI work).
- Request size limits on crawl responses (default 10 MB) to bound resource use.
- All secrets via environment variables (`.env`, never committed;
  `.env.example` documents required keys with placeholder values).

## 7. Provider abstractions already in place

- `app/engines/search/base.py::SearchProvider` — `DuckDuckGoSearchProvider` is
  the only implementation today; swapping in Bing/Serper/Tavily/Google CSE is
  a new class, no caller changes.
- `app/engines/crawler/base.py::PageFetcher` — HTTP-only today (httpx);
  Phase 4 adds a Playwright-backed implementation selected adaptively per URL.

## 8. Risks identified going in

| Risk | Mitigation adopted |
|---|---|
| Building the full 100+ section spec in one sitting produces untested, unreviewed sprawl | Ship a genuinely working vertical slice (Phases 1–3) first; every later phase is additive and documented, not promised-and-faked |
| SSRF via crawler reaching internal infra | Host/IP allowlist check pre-request + per-redirot-hop, see SECURITY.md |
| Claiming "verified"/confidence without real computation | Phase 1–3 confidence score is explicitly a simple, disclosed heuristic (source freshness + HTTP success), not a Truth Engine claim — UI labels it accordingly until Phase 6 lands |
| Search without a paid API key | DuckDuckGo HTML endpoint as default provider; documented as swappable, not a permanent production choice |
| Local dev Python is 3.11, spec asks 3.12+ | Docker image pins `python:3.12-slim`; code avoids 3.12-only syntax so local 3.11 dev still works |

## 9. Benchmark criteria (initial; expanded per Phase 6/Phase 48 of the spec)

Even at this stage, `docs/phases/PHASE_PLAN.md` §"Benchmarking" defines the
metrics the platform will eventually report per research job: precision,
recall, coverage, source diversity, freshness, verification rate, duplicate
rate, latency, cost. Phase 1–3 does not compute these yet (there is nothing
to verify against multiple sources yet) — this section exists so later phases
implement against an agreed rubric instead of inventing metrics ad hoc.
