# AI Research & Web Intelligence Platform

Turn a research goal into an evidence-backed answer. The user states an objective
in natural language; the platform plans the research, discovers sources, crawls
and extracts content, resolves entities, cross-verifies claims across
independent sources, scores confidence, and presents results with full
traceability back to the original source.

This is **not** a scraper with a UI bolted on. It is a research orchestration
engine: search → crawl → extract → normalize → deduplicate → resolve entities →
verify → detect contradictions → score confidence → synthesize → present
evidence. See [ARCHITECTURE.md](./ARCHITECTURE.md) for the full design and
[docs/phases/PHASE_PLAN.md](./docs/phases/PHASE_PLAN.md) for the build order.

## Status

**Phase 1 (Foundation) + Phase 2 (Auth) + Phase 3 (Research Core)** are
implemented and working end-to-end:

```
User → Research request → FastAPI → Redis queue → Worker
     → Search → Crawl (SSRF-guarded) → Extract → Store
     → Live progress (WebSocket) → Results in React UI
```

Everything else in the master spec (knowledge graph, verification/contradiction
engines, MCP server, monitoring, enterprise multi-tenancy, Kubernetes, etc.) is
scoped and documented in the phase plan but **not yet built** — this README
will be updated as each phase lands. Nothing in the UI claims to do more than
the code actually does.

## Stack

| Layer | Choice |
|---|---|
| Backend | Python 3.12, FastAPI, Pydantic v2, SQLAlchemy 2 (async), Alembic |
| Queue/Workers | Redis + [arq](https://github.com/python-arq/arq) (async-native; see ARCHITECTURE.md §"Why arq, not RabbitMQ/Celery") |
| Crawling/Extraction | httpx, BeautifulSoup4, lxml, trafilatura |
| Frontend | Vite, React 18, TypeScript, TailwindCSS, TanStack Query, Zustand, React Router |
| Datastores | PostgreSQL (system of record), Redis (queue + cache + pub/sub) |
| Infra | Docker Compose (dev), GitHub Actions CI |

Future phases add OpenSearch, Qdrant, Neo4j, MinIO, Playwright, Prometheus/Grafana,
OpenTelemetry, Kubernetes manifests — see the phase plan.

## Quick start (Docker)

```bash
cp .env.example .env
docker compose up --build
```

- API: http://localhost:8000 (docs at `/docs`)
- Frontend: http://localhost:5173
- Postgres: localhost:5432, Redis: localhost:6379

## Quick start (local, no Docker)

Backend:

```bash
cd backend
python3 -m venv .venv && source .venv/bin/activate
pip install -e ".[dev]"
cp ../.env.example ../.env   # edit DATABASE_URL / REDIS_URL for local services
alembic upgrade head
uvicorn app.main:app --reload
# in another shell, run the worker:
arq app.workers.worker.WorkerSettings
```

Frontend:

```bash
cd frontend
npm install
npm run dev
```

## Tests

```bash
cd backend && pytest
cd frontend && npm run build   # type-checks + builds
```

## Documentation

- [ARCHITECTURE.md](./ARCHITECTURE.md) — system design, service diagram, data model, provider abstractions
- [docs/phases/PHASE_PLAN.md](./docs/phases/PHASE_PLAN.md) — build order, phase-by-phase scope, risks, benchmark criteria
- [SECURITY.md](./SECURITY.md) — SSRF protections, tenant isolation, secrets handling
- API contract: run the app and see `/docs` (OpenAPI, auto-generated) or [docs/API.md](./docs/API.md)
