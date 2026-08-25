# Phase Plan

Built incrementally. Each phase must be functional before the next starts
(master spec §85, §103). This document is the standing reference for what
"done" means per phase, and is updated as phases land.

## Phase status

| Phase | Name | Status |
|---|---|---|
| 1 | Foundation | ✅ Implemented this session |
| 2 | Authentication | ✅ Implemented this session |
| 3 | Research Core (basic pipeline) | ✅ Implemented this session |
| 4 | Advanced Crawler (Playwright, adaptive, sitemap, API discovery) | Not started |
| 5 | Intelligence (entity resolution, claims, dedup, structured extraction) | Not started |
| 6 | Verification (multi-source, evidence, contradictions, confidence, source scoring) | Not started |
| 7 | Knowledge (OpenSearch, Qdrant, Neo4j, semantic search, knowledge graph) | Not started |
| 8 | AI (AI Gateway, planner/verification/synthesis agents, adaptive research) | Not started |
| 9 | MCP (dedicated MCP server + documented tools) | Not started |
| 10 | Monitoring (change detection, scheduled research, alerts, snapshots) | Not started |
| 11 | Enterprise (multi-tenancy hardening, billing, quotas, K8s, advanced security) | Not started |

## Session 1 verification report

Per master spec §67/§10: implement → test → validate → document → report.
This is that report for Phases 1–3.

**IMPLEMENTED** — FastAPI + async SQLAlchemy 2 + Alembic; Redis + arq queue
and worker; Postgres schema (organizations, users, org membership/RBAC,
research jobs/events/sources/pages/results); JWT auth (register/login/
refresh/me); the search → crawl (SSRF-guarded) → extract → store pipeline;
REST + WebSocket API; Vite/React/TS/Tailwind frontend with a hand-rolled
shadcn-pattern design system, five real (API-wired, no placeholder) screens;
Docker Compose + Dockerfiles; GitHub Actions CI.

**TESTED** — 27 backend pytest cases (unit + integration), including one
that runs the *entire* worker pipeline against a real in-memory DB with only
the network-touching calls stubbed, plus 8 dedicated SSRF-guard cases; ruff
lint + format clean; frontend `tsc -b && vite build` and `eslint` clean.
Beyond the test suite, the stack was run for real — not just unit-tested —
against actual PostgreSQL 16 and Redis 7 (installed directly in the dev
sandbox, since a Docker daemon wasn't available there): Alembic migration
up/down/up against a real Postgres, live `uvicorn` + `arq` processes, an
HTTP walk through register → login → create research → live status
transitions → completion, and a Playwright-driven browser session against
the real Vite dev server exercising register → dashboard (empty state) →
new research → live progress → dashboard (populated). Two real bugs were
caught this way that the SQLite-backed test suite could not have caught, and
are fixed in this session (see below).

**WORKING** — the full vertical slice runs end-to-end against real
infrastructure. Search itself returned zero hits in the sandbox run because
the sandbox's egress policy blocks the DuckDuckGo host (confirmed via the
proxy's own diagnostics, not a code defect) — the pipeline still completed
correctly, logged the failure, and returned a clean empty-result state
rather than crashing or fabricating results, which is the behavior that
matters here (master spec §98).

**Bugs found and fixed via real-infrastructure testing (not caught by
SQLite-backed tests):**

1. **Postgres enum value mismatch.** SQLAlchemy's `Enum` type serializes a
   Python enum by its *name* (`"ADMIN"`) by default, not its *value*
   (`"admin"`) — surprising for a `StrEnum`, where those look interchangeable
   everywhere else in the codebase. The hand-written Alembic migration
   created the native Postgres enum type with lowercase values (matching the
   external API contract), so real inserts failed with `invalid input value
   for enum role: "ADMIN"`. SQLite-backed tests never caught it because
   `Base.metadata.create_all()` derives its CHECK constraint from the same
   (name-based) default, so it was internally self-consistent there. Fixed
   with a shared `pg_enum()` helper (`app/models/base.py`) that sets
   `values_callable` explicitly, used by every enum-backed column.
2. **Duplicate Postgres `CREATE TYPE`.** The migration's explicit
   `role_enum.create(bind, checkfirst=True)` call and SQLAlchemy's automatic
   enum-type creation on `create_table()` for a column of that type both
   fired, and the second one didn't check-first correctly, raising
   `DuplicateObjectError` on a real Postgres target (again invisible against
   SQLite, which has no native enum type to double-create). Fixed by marking
   the migration's enum type objects `create_type=False` so only the
   explicit `.create()`/`.drop()` calls manage them.
3. **Frontend event-timeline duplication.** The live research view merged
   REST-polled events (server `created_at`) with WebSocket-delivered events
   (client-stamped on arrival) and deduped by `kind:created_at` — since the
   two paths stamp different timestamps for the same event, entries could
   appear twice. Caught visually in the Playwright screenshot of a completed
   job. Fixed by deduping on `kind:JSON.stringify(payload)` instead.

Docker itself (`docker compose up`) could not be exercised in this session —
the sandbox has no Docker daemon available — so the Dockerfiles/compose file
are believed correct by inspection and by the fact that the same commands
they run (`alembic upgrade head`, `uvicorn`, `arq`, `npm run dev`/`build`)
were all verified directly, but a literal `docker compose up --build` run is
still owed as a follow-up check in an environment where Docker is available.

**REMAINING** — everything in Phases 4–11 below, as scoped. Within Phase
1–3 itself: no known gaps against what was promised for this slice.

**NEXT** — Phase 4 (Advanced Crawler): Playwright browser worker, adaptive
static/dynamic strategy selection, sitemap/robots.txt awareness, goal-driven
URL prioritization.

## Phase 1 — Foundation

**Scope delivered:** monorepo layout; FastAPI app factory with health check
(DB + Redis liveness); async SQLAlchemy 2 engine/session; Alembic migrations;
Redis client; structured logging with request/job correlation IDs; Docker
Compose (postgres, redis, api, worker, frontend); Vite + React + TS + Tailwind
frontend with a hand-built design-system primitive set (no external shadcn CLI
run, since it needs interactive scaffolding — the primitives follow the same
composition pattern: unstyled Radix behavior + Tailwind classes + `cva`
variants, so `npx shadcn add` remains a drop-in path later); GitHub Actions CI
running backend tests and frontend build.

**Explicitly deferred to later phases:** RabbitMQ/Kafka (using arq+Redis for
now, see ARCHITECTURE.md), OpenSearch/Qdrant/Neo4j/MinIO, Prometheus/Grafana/
OpenTelemetry, Kubernetes manifests.

## Phase 2 — Authentication

**Scope delivered:** `organizations`, `users`, `organization_members` tables;
register/login/refresh/me endpoints; JWT access + refresh tokens; RBAC role
enum (`super_admin, admin, research_manager, researcher, analyst, viewer,
api_client`) carried in the membership row and enforced via a FastAPI
dependency (`require_role(...)`); passwords hashed with bcrypt; every
authenticated request resolves to `(user, organization, role)` and every
downstream query is scoped by `organization_id`.

**Deferred:** API keys, teams (beyond a single flat org-member list), SSO,
session management UI, full audit-log table (event log exists for research
jobs only, not yet a general audit trail — see Phase 11).

## Phase 3 — Research Core

**Scope delivered:** the vertical slice the whole platform is organized
around —

```
POST /api/v1/research {query, mode}
  → ResearchJob row (status=CREATED) written by FastAPI
  → enqueued on arq (status=QUEUED)
  → worker: SEARCHING (DuckDuckGo HTML provider, top N URLs)
  → worker: CRAWLING (httpx, SSRF-guarded, concurrent, per-domain limit)
  → worker: EXTRACTING (trafilatura main-content extraction + bs4 metadata)
  → worker: writes ResearchResult rows, status=COMPLETED
  → progress published on Redis pub/sub at each step
  → GET /research/{id}/ws relays those events live to the browser
  → React "Live Research" view renders progress + arriving results
  → GET /research/{id}/results returns the final list
```

Confidence today is a **disclosed, simple heuristic**
(`0.5 base + 0.3 if HTTP 200 + 0.2 if extracted text length > threshold`) —
the UI labels it "basic relevance score," never "verified," because no
multi-source corroboration exists yet. This is intentional: master spec §98
forbids displaying "Verified" or a confidence percentage implying real
verification when none occurred.

**Deferred:** everything Phase 4+ covers — no browser rendering (static HTML
only), no entity resolution, no cross-source verification, no contradiction
detection, no knowledge graph.

## Phase 4 — Advanced Crawler (next up)

Playwright browser worker pool; adaptive strategy selection (static → HTTP,
dynamic → browser, API detected → structured extraction); sitemap.xml and
robots.txt-aware crawling; goal-driven URL prioritization (score pages by
likely relevance to the requested fields before crawling them); response
caching in Redis; per-domain rate limiting.

## Phase 5 — Intelligence

Structured extraction against a user-defined schema; entity extraction
(company/person/product/location); entity resolution (alias clustering —
"Company X" / "Company X Ltd" / domain match); claim extraction (subject–
predicate–object with year/unit); deduplication (URL, content-hash, near-
duplicate via simhash, syndicated-content detection).

## Phase 6 — Verification

Multi-source corroboration (≥3 independent sources for "verified" at maximum
verification level); Evidence Engine linking every claim to its source
excerpt; Contradiction Engine (flag conflicting values, never hide them);
Truth Engine states (`VERIFIED, CORROBORATED, PROBABLE, UNCERTAIN,
CONTRADICTED, OUTDATED, UNVERIFIABLE`); multidimensional confidence score
(authority, relevance, freshness, evidence, consistency, source diversity,
completeness) with an explainable breakdown, not just a number.

## Phase 7 — Knowledge

OpenSearch for full-text search across crawled content; Qdrant for semantic/
vector search over extracted claims and documents; Neo4j for the knowledge
graph (Company/Person/Product/Country/Investor/Document/Source/Claim/Event
nodes; FOUNDED/CEO_OF/INVESTED_IN/... edges); MinIO for document and page
snapshot storage (enables the "compare historical snapshot" feature).

## Phase 8 — AI

AI Gateway abstraction (model/provider/temperature/fallback-chain, cost
tracking); Research Planner agent (turns the NL request into the structured
plan the UI shows for review); Verification/Synthesis agents; adaptive
research loop (gap analysis → new targeted queries → re-verify → stop
condition). Explicit rule carried from master spec §51/§43: web content
extracted during crawling is always treated as untrusted data passed to an
agent's *context*, never as instructions the agent executes.

## Phase 9 — MCP

Dedicated MCP server process exposing: `create_research, get_research,
search_web, discover_sources, crawl_url, crawl_domain, extract_content,
extract_document, extract_entities, extract_claims, verify_claim,
compare_sources, resolve_entity, get_evidence, calculate_confidence,
query_knowledge_graph, export_dataset, monitor_source`. Documented in
`docs/MCP.md` once built.

## Phase 10 — Monitoring

Monitor definitions (URL/domain/keyword/entity/document); scheduled research
jobs; change detection (snapshot diffing); alert delivery (webhook, email,
in-app notification).

## Phase 11 — Enterprise

Full audit trail (immutable, all mutating actions); API keys; usage/cost
records per research job; billing hooks; quota enforcement per organization;
Kubernetes manifests; horizontal worker scaling; advanced security review
(pen-test checklist, dependency scanning in CI).

## Dependencies between phases

Phase 6 (Verification) needs Phase 5 (entities/claims) to have something to
verify. Phase 7's Neo4j graph needs Phase 5's entity resolution to avoid a
graph full of duplicate nodes. Phase 8's agents should not be built before
Phase 6's Truth Engine exists, or "AI-adaptive" research has no ground truth
to adapt toward. Phase 9's MCP tools are thin wrappers over Phase 3–8
services — building MCP earlier just means re-wrapping it later. This is why
the order above is load-bearing, not arbitrary.

## Benchmarking (target rubric, implemented incrementally from Phase 6 on)

Per research job, once Phase 6 lands:

- **Precision** — of returned results, fraction that hold up on manual spot-check
- **Recall** — against a hand-curated gold set for a benchmark query, fraction found
- **Coverage** — fraction of requested schema fields populated
- **Source diversity** — distinct independent domains cited per claim
- **Freshness** — median age of cited evidence
- **Verification rate** — fraction of claims reaching `VERIFIED`/`CORROBORATED`
- **Duplicate rate** — near-duplicate sources counted as independent (should be ~0)
- **Latency** — wall-clock per research mode (quick/balanced/deep/...)
- **Cost** — HTTP requests, browser-minutes, LLM tokens, storage per job

A `benchmarks/` directory with fixed gold-set queries will be added in Phase 6
alongside the Verification Engine so these numbers are computed, not asserted.

## Risks tracked

See ARCHITECTURE.md §8. Re-evaluated at the start of each phase.
