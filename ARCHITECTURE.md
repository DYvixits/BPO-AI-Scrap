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
          │  Search    │ │  Crawler   │ │ Extraction │  2 passes: trafilatura
          │  Engine    │ │  Engine    │ │  Engine    │  main-content text +
          │(provider   │ │(httpx, SSRF│ │(trafilatura│  structured.py (JSON-LD,
          │ abstraction│ │ guarded)   │ │ + bs4/lxml)│  OG tags, contact info) —
          └─────▲──────┘ └──────┬─────┘ └──────┬─────┘  dedup.py's near-duplicate
                │               │ same-domain           │ check runs against pass 1's
                │               │ links found on         │ text (URL-normalization
                │               │ each crawled page       │ dedup runs earlier, in the
                │        ┌──────▼──────┐                  │ frontier itself)
                │        │  Crawl      │  NextBestURL priority frontier:
                │        │Prioritization│ score_candidate() ranks pages by
                │        │  (frontier) │ objective fit; InformationGain-
                │        └─────────────┘ Tracker stops the crawl early once
                │                        required_attributes are satisfied  │
                │                                                           ▼
                │                                                   ┌───────────────┐
                │                                                   │    Entity      │  runs once, after
                │                                                   │  Resolution    │  crawling ends: groups
                │                                                   │   Engine       │  pages into Company
                │                                                   └───────┬───────┘  rows (same-domain, then
                │                                                           │           cross-domain name match)
                │                                                           ▼
                │                                                   ┌───────────────┐
                │                                                   │ Verification   │  per company: source
                │                                                   │    Engine      │  count/diversity/
                │                                                   └───────────────┘  freshness -> a Truth
                │                                                                       Engine status + evidence
                │ N queries (deduped by URL)
          ┌─────┴──────┐
          │  Search    │  builds up to MAX_QUERIES=4 targeted
          │  Strategy  │  queries from a ResearchObjective
          │  Engine    │  (app/engines/search_strategy)
          └─────▲──────┘
                │ ResearchObjective
          ┌─────┴──────┐
          │   Query    │  heuristic NL parser — no LLM call yet
          │Intelligence│  (industry/geography/size/signals/...),
          │  Engine    │  runs once at job creation, before enqueue
          └────────────┘  (app/engines/query_intelligence)
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
│   │   │   ├── query_intelligence/ # NL query -> ResearchObjective (heuristic, no LLM)
│   │   │   ├── search_strategy/    # ResearchObjective -> up to 4 targeted queries
│   │   │   ├── search/             # SearchProvider abstraction + DuckDuckGo impl
│   │   │   ├── crawler/            # HTTP crawler + SSRF guard + link discovery
│   │   │   │                       # + goal-driven prioritization (NextBestURL)
│   │   │   │                       # + URL normalization (dedup layer 1)
│   │   │   ├── extraction/         # trafilatura main-content text pass +
│   │   │   │                       # structured.py (JSON-LD/OG/contact, pass 2)
│   │   │   │                       # + dedup.py (near-duplicate shingle/Jaccard)
│   │   │   ├── entity_resolution/  # resolver.py — groups crawled pages into
│   │   │   │                       # Company rows (same-domain, then
│   │   │   │                       # cross-domain exact name match)
│   │   │   └── verification/       # engine.py — per-Company confidence score
│   │   │                           # from source count/diversity/freshness
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
  config (jsonb — max_results: how many search hits seed the crawl
    frontier; max_pages: the crawl's actual page budget, since Phase 3 the
    worker can follow same-domain links beyond the initial hits, not just
    re-fetch them; min_sources; ...),
  objective (jsonb — the ResearchObjective the Query Intelligence Engine
    parsed the query into: target_entities, geography, industry,
    company_size_min/max, required_attributes, signals, freshness, and
    matched_keywords for explainability; set once at creation, never
    mutated; rendered client-side as "Understood as:" chips),
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
  content_hash, title, extracted_text,
  structured_data (jsonb — the second extraction pass's output:
    json_ld, meta_description, og_title/description/site_name, emails,
    phones — see engines/extraction/structured.py),
  extracted_at, error

research_results
  id (uuid pk), organization_id fk, research_job_id fk, crawl_page_id fk (nullable),
  company_id fk (nullable, → companies; set once by the Entity Resolution
    Engine after crawling ends — null for results that predate resolution
    or whose page yielded no usable company name),
  title, url, snippet, confidence (float, currently source/freshness-based —
  see PHASE_PLAN §6 for the full multi-source Truth Engine), created_at

companies
  id (uuid pk), organization_id fk, research_job_id fk, canonical_name (text),
  primary_domain, description (nullable),
  match_confidence (float — 1.0 for a single-domain company, 0.7 for a
    cross-domain merge on a name match; a disclosed heuristic number, not a
    verified claim, see SECURITY.md), created_at
  # scoped per research_job, not deduplicated across jobs or the wider org

entity_aliases
  id (uuid pk), organization_id fk, company_id fk, alias_type (text:
    "name" | "domain"), value, source_url, created_at
  # every distinct candidate name and every merged domain, with the page
  # it came from — the resolver's evidence trail

evidence
  id (uuid pk), organization_id fk, company_id fk, source_url, domain,
  excerpt (nullable), created_at
  # one row per crawled page counted toward a company's confidence score
  # (app/engines/verification) — page-level, not claim-level; see that
  # module's docstring for why

confidence_scores
  id (uuid pk), organization_id fk, company_id fk (unique — one row per
    company), status (enum: unverifiable|uncertain|corroborated|verified|
    outdated), source_count, source_diversity, freshness_score,
    evidence_completeness, overall_score, created_at
  # the Verification Engine's output: 5 of the master spec's 7 Truth
  # Engine states, computed from source count/diversity/freshness alone
  # — no claim-level agreement/contradiction detection (PROBABLE and
  # CONTRADICTED are not computed), a disclosed scope limit, not an
  # oversight
```

All tables use UUID primary keys and are scoped by `organization_id` for
tenant isolation. `organization_id` is denormalized directly onto
`research_events`/`sources`/`crawl_pages`/`research_results`/`companies`/
`entity_aliases`/`evidence`/`confidence_scores` (rather than living only on
`research_jobs` and requiring a join) for two reasons: it keeps app-layer
filters and indexes simple, and it's what makes PostgreSQL Row-Level
Security on those tables a plain equality check instead of a subquery —
see SECURITY.md §"Tenant isolation" for the full RLS design, including why
`research_jobs` itself is deliberately excluded from RLS.

`research_jobs.status` state machine (subset of the full 71-state spec target):

```
CREATED → QUEUED → SEARCHING → CRAWLING → EXTRACTING → COMPLETED
                                                       ↘ FAILED
```

Since Phase 3, crawling and extraction happen together per page (each
wave of the priority frontier fetches, extracts, and stores before the
next wave is even scored) — there's no longer a real "all fetching done,
now extracting" batch boundary. `CRAWLING` covers the whole frontier loop;
`EXTRACTING` is emitted as a brief final step once it ends, so the status
sequence stays honest about what's actually happening rather than
claiming a separate phase that no longer exists as a batch.

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
GET    /api/v1/research/{id}/companies  → resolved companies for this job,
                                           each with its confidence_score
                                           and evidence (Phase 6)
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
- `app/engines/crawler/fetcher.py::PageFetcher` — HTTP-only today (httpx);
  a Playwright-backed implementation selected adaptively per URL is still
  open (AUDIT_BPO_CRM.md's Phase 3 remainder — adaptive strategy selection
  was descoped from Phase 3's session to just goal-driven prioritization).
- `app/engines/query_intelligence/parser.py::parse_query` — keyword-table
  driven (`keywords.py`), deliberately not an LLM call in this phase (see
  PHASE_PLAN.md — the AI Gateway is sequenced after Phase 6 Verification
  exists, so early scoring never depends on an unaudited black box). Every
  match is recorded in `matched_keywords`, so the parse is explainable by
  construction rather than by after-the-fact justification.
- `app/engines/search_strategy/strategy.py::build_queries` — turns one
  `ResearchObjective` into up to `MAX_QUERIES=4` targeted search queries;
  results across queries are deduplicated by URL before crawling.
- `app/engines/crawler/links.py::extract_links` — parses same-registrable-
  domain `<a href>` links out of a fetched page's HTML (deduplicated,
  fragment-stripped, asset/mailto/tel/javascript links filtered out). Feeds
  the crawl frontier; deliberately does not cross domains — that's Source
  Discovery's job (still a Phase 2 open item), not link-following's.
- `app/engines/crawler/prioritization.py::score_candidate` — NextBestURL
  scoring: ranks a candidate URL by how well its path/anchor text matches
  the objective's `required_attributes` (a curated, disclosed keyword table,
  `ATTRIBUTE_PAGE_SIGNALS`, in the same spirit as `keywords.py`), decayed by
  crawl depth. `InformationGainTracker` reuses the Query Intelligence
  Engine's own `ATTRIBUTES` keyword table to detect, per crawled page,
  which required attributes were actually found — the worker stops a job
  early once every required attribute has been satisfied, or after a run
  of pages that found nothing new (`_STALL_LIMIT`/`_STALL_FLOOR` in
  `app/workers/tasks/research.py`). Disabled entirely (falls back to the
  page-budget-only behavior from before this phase) when the objective has
  no `required_attributes` to look for.
- `app/engines/crawler/normalize.py::normalize_url` — dedup layer 1
  (AUDIT_BPO_CRM.md Phase 4): strips known tracking parameters (`utm_*`,
  `fbclid`, `gclid`, ...), sorts remaining query params, strips trailing
  slashes and fragments, lowercases scheme/host (never the path — path
  case can be server-meaningful). Used as the frontier's dedup key at push
  time, so a tracking-param variant of an already-queued URL never
  occupies a frontier slot or a crawl-budget page.
- `app/engines/extraction/structured.py::extract_structured_data` —
  the second extraction pass: parses `<script type="application/ld+json">`
  blocks, Open Graph / meta description tags, and plain-text email/phone
  matches. Every field is either literally present in the markup or a
  direct regex match against visible text — nothing here is inferred.
- `app/engines/extraction/dedup.py::NearDuplicateDetector` — dedup layer
  3 (after URL normalization and exact content-hash matching): shingles
  each page's extracted text into overlapping 5-word sequences and flags
  a page as a near-duplicate once its Jaccard similarity to any
  already-seen page in the same job crosses 0.9 — catches pages that
  differ only by a timestamp or session token embedded in otherwise
  identical markup, which exact-hash matching alone would miss. Scoped to
  one job at a time, not a cross-job or cross-tenant cache.
- `app/engines/entity_resolution/resolver.py::resolve_companies` — Phase 5:
  a disclosed two-step heuristic, not ML/fuzzy matching. Step 1 groups
  crawled pages by registrable domain (already correct by construction,
  since the crawler only follows same-domain links). Step 2 merges
  domain-groups into one company when their best-guess names — read from
  JSON-LD `Organization`, then Open Graph site name, then page title, in
  that order, same pattern as `structured.py` — are identical after
  normalization (lowercased, legal-suffix-stripped, punctuation-stripped).
  `match_confidence` is 1.0 for an unmerged single-domain company, 0.7 for
  a cross-domain name-match merge — a disclosed number, not a verified
  claim. Runs once per job, after crawling ends, in
  `app/workers/tasks/research.py`.
- `app/engines/verification/engine.py::compute_confidence` — Phase 6: a
  disclosed, source-count-based confidence score for each resolved
  Company, computed from the same crawled pages Entity Resolution just
  grouped (source_count/source_diversity/freshness_score/
  evidence_completeness). `status` is 5 of the master spec's 7 Truth
  Engine states (`UNVERIFIABLE, UNCERTAIN, CORROBORATED, VERIFIED,
  OUTDATED`) — `PROBABLE`/`CONTRADICTED` are not computed, since both
  need claim-level agreement/conflict detection that this codebase's
  claim extraction (still MISSING, per AUDIT_BPO_CRM.md's target-services
  table) doesn't provide yet. A company is never `VERIFIED` without at
  least `VERIFIED_MIN_DOMAINS` (3) independent domains, per master spec
  §98. Runs once per company, immediately after Entity Resolution writes
  it, in the same worker loop.

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
