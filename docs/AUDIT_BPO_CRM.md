# Audit — Repositioning as the BPO Commercial Intelligence Platform

**Phase 0 deliverable.** No code changes in this document — per instruction,
this is audit + target architecture + phase plan only. It supersedes the
generic "AI Research & Web Intelligence Platform" framing in
`ARCHITECTURE.md`/`docs/phases/PHASE_PLAN.md` with a commercial-intelligence
lens (BPO = Business Pro Operator, the CRM this platform feeds), while
keeping everything already built as the foundation — this is **EXTEND**,
not a rewrite.

## 0. Where this repo actually is right now

Everything below the "target" sections assumes the Phase 1–3 slice already
built this session: FastAPI + async SQLAlchemy 2/Alembic on PostgreSQL,
Redis + arq queue/worker, JWT auth with org-scoped RBAC, an httpx crawler
with an SSRF guard, trafilatura-based extraction, a DuckDuckGo search
provider, a Vite/React/TS/Tailwind frontend with 5 real screens, Docker
Compose, GitHub Actions CI. 27 tests pass; the stack was verified running
end-to-end against real Postgres/Redis (not just SQLite-backed tests) —
see `docs/phases/PHASE_PLAN.md`'s "Session 1 verification report" for
specifics, including two real bugs a live-DB run caught. **This work is
committed locally on `feature/phase1-foundation` but not yet pushed** — the
GitHub App doesn't have write access to `DYvixits/bpo-ai-scrap` yet; you
said you'd fix that and I'd push. Nothing here is lost — the audit and this
push are independent, and I'm not blocked on the push to do the audit.

## 1. Audit by category

Legend: **REUSE** = keep as-is or nearly so · **EXTEND** = keep the
shape, add to it · **REFACTOR** = keep the concept, change the
implementation · **REPLACE** = concept no longer fits, swap it ·
**MISSING** = does not exist yet.

### Frontend architecture — REUSE / EXTEND

Vite + React 18 + TS + Tailwind, feature-folder layout
(`src/{app,components/ui,features,pages,layouts,stores,services,types}`),
hand-rolled shadcn-pattern design system (Button/Card/Input/Badge/Progress/
Skeleton/Textarea/Label — Radix primitives + `cva` + `cn()`), TanStack Query
for server state, Zustand (persisted) for auth token, React Router. This
layout is exactly the "modular, feature-organized, not generic-folder" shape
§38 of the earlier spec and this new one both ask for. **Nothing here needs
replacing.** New screens (Result Explorer, Company Intelligence Page, Why
This Lead, Advanced Mode) are additions under `features/` and `pages/`, not
restructuring.

### Backend architecture — REUSE / EXTEND

`backend/app/{core,models,schemas,repositories,services,engines,workers,
api/v1,integrations}`. The `engines/` directory already anticipates the
target's plugin-style engine model (`engines/search/base.py::SearchProvider`,
`engines/crawler/{fetcher,ssrf_guard}.py`, `engines/extraction/content.py`)
— each is an ABC-backed interface with one concrete implementation today,
documented as swappable. This is the right shape to grow into the 26
logical services (§3 of the new spec) as more `engines/*` and `services/*`
modules, not a different architecture.

### Folder structure / components — REUSE

No generic "utils dump" or "misc" folders; one file per concern. Matches
target norms as-is.

### API — EXTEND

Exists: `/api/v1/{auth,research,health}` with 8 routes (register, login,
refresh, me, create/list/get research, get results, WS live feed). Target
adds `/api/v1/{sources,entities,companies,signals,opportunities,evidence,
tenants,crm}` — all **MISSING**, all additive (no existing route needs to
change shape). `docs/API.md` already documents the pattern to follow
(request/response JSON examples, auth/scoping notes) — extend it per new
route, don't restart it.

### Data models / DB / migrations — EXTEND, one REFACTOR

Exists: `organizations, users, organization_members (RBAC role), research_
jobs, research_events, sources, crawl_pages, research_results` — all UUID
PKs, `organization_id`-scoped, indexed, one Alembic migration
(`0001_initial.py`), verified up/down/up against real Postgres.

**MISSING** (net-new tables, all additive — no existing table's shape
needs to change): `companies`, `people` (contacts/decision-makers), `claims`,
`evidence`, `signals`, `entity_aliases` + `entity_match_confidence`,
`conflict_records`, `fit_scores`, `intent_scores`, `confidence_scores`,
`opportunity_scores` (see §6 below — kept as **separate** tables per your
scoring note, not one blended column), `tenant_tiers`/`tenant_quotas`,
`crm_sync_records`, `audit_log` (a real one — today's `research_events` is
job-scoped progress, not a general audit trail).

**One REFACTOR**: `research_results.confidence` is currently a single float
computed by a disclosed placeholder heuristic (`app/services/confidence.py`
— explicitly documented as "not a verified claim," per the earlier spec's
anti-fake-data rule). Once `fit_scores`/`intent_scores`/`confidence_scores`/
`opportunity_scores` exist as their own tables (§6), this column is retired
in favor of joining to `opportunity_scores` — a schema migration, not a
rewrite of the pipeline around it.

Migration discipline (expand → migrate → contract, §53 of the new spec) is
not yet formalized — one migration so far, nothing to contract yet. Adopt
the discipline starting with the first schema-adding migration in Phase 1.

### Auth / authorization — REUSE, EXTEND for tiers

JWT access+refresh (HS256), bcrypt password hashing, RBAC role enum
(`super_admin…api_client`) carried on `organization_members`, resolved
fresh from the DB per request (not trusted from the JWT's own role claim —
see `app/core/deps.py`). This is solid and matches target requirements
directly. **MISSING**: API keys for programmatic/CRM-integration access
(`api_client` role already exists in the enum, unused so far), tenant
tiers/quotas (§37/38 of the new spec).

### Multitenancy — PARTIAL, REFACTOR for defense-in-depth

Today: every repository query is `organization_id`-scoped, and that ID is
**derived server-side from the JWT** (`AuthContext.organization_id` in
`app/core/deps.py`), never trusted from a client-supplied parameter — this
is exactly what §36 of the new spec demands ("NE JAMAIS faire confiance au
tenant_id fourni directement par le frontend"). There's a dedicated test
proving cross-org isolation
(`test_organizations_cannot_see_each_others_research`). What's missing is
**defense in depth**: this isolation lives entirely in the application
layer today, with no PostgreSQL Row-Level Security backing it up — a bug in
a future repository function could leak across tenants with nothing at the
DB layer to stop it. **REFACTOR**: add RLS policies keyed on
`organization_id` (set via `SET LOCAL app.current_tenant` per request) as a
second, independent layer — the app-layer scoping stays, RLS makes it
non-optional.

### Scraping / crawling — REUSE as MVP, EXTEND is the biggest gap

Exists: async httpx fetcher with a real SSRF guard (DNS-resolves and
rejects private/loopback/link-local/reserved ranges, re-checked per
redirect hop, response-size capped, documented residual DNS-rebinding gap),
trafilatura-based content extraction. This is a legitimate, tested Phase-1
crawler — keep it as the `HTTP` strategy.

**MISSING**, and this is where most of the new spec's value lives:
adaptive strategy selection (Playwright for JS-heavy, API-JSON detection,
sitemap/RSS/JSON-LD/PDF handling), goal-driven `PagePotentialScore` /
`NextBestURL` prioritization, `InformationGainScore`, early stopping on
diminishing returns, multi-provider `SourceProvider` abstraction (today
there is exactly one: DuckDuckGo HTML, documented as swappable but not yet
swapped). None of this requires discarding the existing fetcher — it becomes
one strategy inside an adaptive dispatcher.

### Workers / queues — REUSE for now, revisit at scale

arq (async, Redis-backed) — chosen explicitly over Celery/RabbitMQ for
Phase 1 to minimize moving parts (`ARCHITECTURE.md` §2). Single job type
today (`run_research_job`). The new spec's fair-scheduling / priority-queue
/ per-tenant-quota requirements (§38) are real gaps, but they're arq
*configuration and job-design* problems (priority queues, per-tenant job
concurrency caps) before they're a "must migrate to Celery" problem — arq
supports job priorities and can be sharded per tenant tier. **Recommendation:
extend arq with tenant-aware scheduling first; only replace it if a concrete
scaling ceiling is hit.** Flagging this as a judgment call, not a fact —
worth confirming before locking the phase plan.

### Cache — MISSING as a distinct layer

Redis is in use for the queue and pub/sub, but nothing is cached yet
(search results, source metadata, computed scores). Straightforward
addition once there's something worth caching (Phase 3+ of the new plan).

### Search (full-text/vector/graph) — MISSING

No OpenSearch, Qdrant, or Neo4j. Given upfront: **these are valuable
optimizations once there's enough data to need them, not prerequisites for
the platform's core value.** The scoring/evidence/CRM pipeline this spec is
really about (§6 below) works on PostgreSQL alone at the data volumes an
early BPO CRM integration will have. Recommend sequencing these behind the
scoring/verification/CRM work, not in front of it (see §7).

### AI / LLM — MISSING entirely

No `ModelRouter`, no structured-output extraction passes. Genuinely
net-new (Phase 9 territory). The existing extraction pipeline
(`engines/extraction/content.py`) is the right seam to add multi-pass
extraction behind, once it exists.

### Logs / monitoring / observability — PARTIAL

Structured logging with a request-correlation filter exists
(`app/core/logging.py`). **MISSING**: Prometheus/Grafana/OpenTelemetry,
per-tenant/per-job tracing, the KPI dashboard (§32/47 of the new spec).

### Tests — REUSE, genuinely solid foundation

27 tests: auth (register/login/refresh/duplicate-email/wrong-password),
research CRUD + **tenant isolation** (the exact test the new spec asks
for in principle), SSRF guard (8 cases including a mocked DNS-rebinding
check), and one full pipeline integration test that exercises search→crawl→
extract→store→confidence→dedup against a real (in-memory) DB with only
network calls stubbed. This test structure (stub the network boundary,
keep everything else real) is the right pattern to keep extending —
apply it to Signal/Fit/Intent/Opportunity engine tests too, not database
mocks.

### Security — REUSE, real gaps remain

SSRF guard (with an honestly-documented residual gap, not a claimed
complete fix — see `SECURITY.md`), bcrypt, JWT, org-scoped queries, secrets
via env vars only (`.env.example`, no hardcoded values), CORS configured.
**MISSING**: rate limiting, RLS (see multitenancy above), secrets manager
integration (currently plain env vars — fine for Phase 1, not for
production), dependency/container scanning in CI, sandboxed browser
workers (moot until Playwright lands).

### Performance — REUSE the pattern, EXTEND the coverage

Async I/O throughout, concurrent crawling bounded by a semaphore, streamed/
capped response bodies, no `SELECT *`, indexed FKs. **MISSING**: caching,
batching/bulk writes (today each crawl page is its own commit — fine at
Phase-1 volumes, will need batching once crawl volume grows), cursor-based
pagination (list endpoints are unpaginated today — fine at current scale,
a real gap once a tenant has hundreds of research jobs), priority queue /
Bloom filter dedup (today's dedup is exact content-hash match only).

### Tech debt (self-assessed, not externally imposed)

The `research_results.confidence` heuristic is the one piece of the
current code that's explicitly a placeholder rather than a real
implementation — and it says so in its own docstring. No other shortcuts
were taken. Unpaginated list endpoints and per-row commits in the worker
loop are the two "fine for now, will need revisiting" items above.

### UX/UI — REUSE the system, EXTEND the screens

Design tokens (HSL CSS variables, light-first, dark-mode-ready shell not
yet wired), the 5 existing screens (login/register/dashboard/new-research/
research-detail) already follow the target's UX principles: empty state
with a call to action (not a blank page), human error state with "what you
can do," live progress via WebSocket+event timeline, a disclosed (not
fabricated) confidence label. **MISSING**: Advanced Mode, Result Explorer
(table/cards/filters/virtualized list/saved views/bulk actions/export),
Company Intelligence Page, "Why This Lead," CRM push UI.

### Deployment / Docker / CI-CD — REUSE, EXTEND for prod

`docker-compose.yml` (postgres/redis/api/worker/frontend dev), per-service
Dockerfiles, GitHub Actions (backend ruff+pytest, frontend eslint+build).
**MISSING**: Kubernetes manifests, staging/production compose or Helm
variants, security/container scanning in CI, a production frontend build
stage (today's frontend Dockerfile is dev-server-only by design, documented
as such).

## 2. Recommendation: EXTEND → REFACTOR → REPLACE, confirmed

Nothing audited above calls for a rewrite. The two REFACTOR items (RLS as a
second isolation layer; retiring the placeholder confidence column once
real scoring tables exist) are both additive migrations, not architectural
breaks. Everything else is either reuse-as-is or net-new addition.

## 3. Target: 26 logical services, mapped to current reality

| Service | Status |
|---|---|
| API Gateway / API Layer | REUSE — FastAPI, `api/v1/router.py` |
| Authentication & Authorization | REUSE — JWT+RBAC |
| Tenant Management | EXTEND — add tiers/quotas table; REFACTOR — add RLS |
| Research Orchestrator | EXTEND — exists as `research_orchestrator.py`, needs `ResearchObjective` NL parsing (currently takes `query`+`mode` directly, no NL→structured-objective step) |
| Search Strategy Engine | MISSING — today's orchestrator issues one search call; needs multi-query generation per §5 of the new spec |
| Source Discovery Engine | MISSING — `SearchProvider` ABC exists with 1 implementation; needs the multi-provider registry with authority/reliability/freshness/coverage/cost scoring |
| Crawl Scheduler | MISSING — today's crawl is a flat concurrent fetch of all discovered URLs, no prioritization |
| Adaptive Crawler | PARTIAL — HTTP-only strategy exists; Playwright/API/sitemap/RSS/PDF strategies missing |
| Content Extraction Engine | REUSE/EXTEND — trafilatura-based, needs multi-pass (§29) |
| Entity Resolution Engine | MISSING |
| Data Enrichment Engine | MISSING |
| Verification Engine | PARTIAL — `app/engines/verification` computes a company-level, source-count-based confidence score (5 of 7 Truth Engine states); `confidence.py`'s per-page placeholder still exists separately, deliberately not retired (see Phase 6 row below) |
| Evidence Engine | PARTIAL — an `evidence` table exists, but it's page-level (which crawled pages support a company), not claim-level; no `Claim` table, so no claim-to-excerpt linking yet |
| Commercial Signal Engine | MISSING |
| Intent Engine | MISSING |
| Fit Scoring Engine | MISSING |
| Opportunity Scoring Engine | MISSING |
| Temporal Intelligence Engine | MISSING |
| Knowledge Graph Engine | MISSING, sequence last (§7) |
| AI/LLM Orchestrator | MISSING |
| Result Ranking Engine | PARTIAL — results ordered by the placeholder confidence today |
| CRM Integration Engine | MISSING |
| Feedback / Learning Engine | MISSING |
| Notification Engine | MISSING |
| Audit Engine | PARTIAL — `research_events` is job-progress logging, not a general audit trail |
| Observability Engine | PARTIAL — structured logs only, no metrics/traces |

## 4. Scoring architecture — confirming your FIT/INTENT/CONFIDENCE split

Agreed, and this is the highest-leverage design decision in the whole
spec: **do not blend these into one number.** Concretely, as separate
tables (not columns bolted onto `companies`), each with its own
explainability:

```
fit_scores          (company_id, tenant_id, score, weights_used, factors[], computed_at)
intent_scores        (company_id, tenant_id, score, contributing_signals[], computed_at)
confidence_scores    (claim_id | company_id, score, source_count, source_diversity,
                       agreement, contradiction_flag, computed_at)
opportunity_scores   (company_id, tenant_id, fit_score_id, intent_score_id,
                       confidence_score_id, freshness, momentum, score, computed_at)
```

`OPPORTUNITY = f(FIT, INTENT, CONFIDENCE, FRESHNESS, MOMENTUM)` — `f` itself
is a per-tenant-configurable weighted function (Configuration Engine, §56),
not hardcoded, so different BPO CRM tenants can weight these differently
(e.g. a tenant selling to fast-moving startups might weight MOMENTUM higher
than a tenant selling multi-year enterprise contracts). Every score row
carries its `factors[]`/`contributing_signals[]` so "Why This Lead" (§23)
and "Why?" (§45) are a join, not a separate black-box explanation system.

This directly reuses the existing `research_results.confidence` retirement
noted in §1 — that column's replacement *is* this table set.

## 5. Multitenancy hardening plan

1. Add `tenant_tiers` (`standard/pro/business/enterprise`) and
   `tenant_quotas` (crawl concurrency, AI budget, storage, worker priority)
   tables, FK'd from `organizations`.
2. Add PostgreSQL RLS policies on every tenant-scoped table, enabled via
   `SET LOCAL app.current_tenant = :org_id` set once per request in a
   FastAPI dependency (alongside, not instead of, today's app-layer
   `organization_id` filtering).
3. Extend the tenant-isolation test pattern already in
   `tests/test_research.py` to cover every new table as it's added — this
   is cheap given the pattern already exists.
4. Fair scheduling: tag arq jobs with `organization_id` and enforce a
   per-tenant in-flight job cap before considering a queue/broker swap.

## 6. Revised phase plan

The spec's Phase 0–15 order is sound but front-loads infrastructure
(Knowledge Graph is Phase 10, before CRM integration at Phase 11) that
isn't needed to deliver the core value proposition. Recommended sequencing
below keeps the same phase *names* but reorders two of them — **flagging
this as a proposal to confirm, not a decision made unilaterally**:

| Phase | Scope | State |
|---|---|---|
| 0 | Audit (this document) | ✅ done |
| 1 | Foundation + multitenancy hardening (RLS, tenant tiers/quotas) | ✅ Done — see `docs/phases/PHASE_PLAN.md`'s Session 2 verification report |
| 2 | Research Orchestrator (NL→`ResearchObjective`, multi-query Search Strategy Engine, multi-provider Source Discovery) | NL→`ResearchObjective` parsing + multi-query Search Strategy Engine ✅ done — see `docs/phases/PHASE_PLAN.md`'s Session 3 verification report; multi-provider Source Discovery not started (still DuckDuckGo-only) |
| 3 | Crawler Engine (adaptive strategy, goal-driven prioritization, NextBestURL, information gain, early stopping) | Goal-driven prioritization (NextBestURL scoring, same-domain link discovery, information-gain early stopping) ✅ done — see `docs/phases/PHASE_PLAN.md`'s Session 4 verification report; adaptive strategy selection (Playwright for JS-heavy pages, sitemap/RSS/JSON-LD/PDF discovery) not started |
| 4 | Extraction + Deduplication (multi-pass extraction, 6-level dedup) | Multi-pass extraction (trafilatura text + JSON-LD/OG/contact structured data) + 3-layer dedup (URL normalization, exact-hash, near-duplicate shingle/Jaccard) ✅ done — see `docs/phases/PHASE_PLAN.md`'s Session 5 verification report; "6-level dedup" was never broken down anywhere in this repo's docs, so 3 more levels remain undefined, not just unimplemented |
| 5 | Entity Resolution | Company-only entity resolution (same-registrable-domain grouping + cross-domain merge on exact normalized-name match, `match_confidence` 1.0/0.7) ✅ done — see `docs/phases/PHASE_PLAN.md`'s Session 6 verification report; person-entity resolution (same person across pages/sources) not started |
| 6 | Verification + Evidence (retires the placeholder confidence column) | Company-level, source-count-based verification (per-company `confidence_scores` + page-level `evidence`, 5 of 7 Truth Engine states — `UNVERIFIABLE/UNCERTAIN/CORROBORATED/VERIFIED/OUTDATED`) ✅ done — see `docs/phases/PHASE_PLAN.md`'s Session 7 verification report; `PROBABLE`/`CONTRADICTED` and all claim-level agreement/contradiction detection not started (needs claim extraction, still MISSING); the Phase 1–3 placeholder `research_results.confidence` was deliberately *not* retired — see that report's REMAINING section for why |
| 7 | Commercial Signals + Temporal Decay | Not started |
| 8 | **Fit + Intent + Opportunity Scoring** (moved up from implicit position — this is the CRM-facing payoff) | Not started |
| 9 | **CRM Integration** (export/push/dedup-against-CRM) — *moved up from Phase 11*: a tenant gets value from Phases 2–8 landing in their CRM well before a knowledge graph exists | Not started |
| 10 | AI Orchestrator (ModelRouter, structured multi-pass extraction) | Not started |
| 11 | Knowledge Graph (Neo4j) — *moved down from Phase 10*: valuable for relationship-heavy queries (buying-committee graphs), not a prerequisite for scoring or CRM push | Not started |
| 12 | Feedback / Learning loop (`P(conversion | signals)`) | Not started |
| 13 | Performance optimization (caching, batching, priority queues, Bloom filters) | Ongoing baseline in place |
| 14 | Security hardening (rate limiting, secrets manager, scanning) | Baseline in place |
| 15 | Production deployment (K8s, staging/prod, CDN/WAF, backup/DR) | Dev-only today |

## 7. Risks

- **Legal exposure is higher for a commercial lead-gen product than a
  generic research tool** — scraping for resale/commercial use draws more
  ToS and data-protection scrutiny (GDPR-adjacent rules apply to any EU-
  connected person data collected) than the earlier "research assistant"
  framing. Recommend a dedicated compliance pass (per-source ToS review,
  personal-data handling policy, retention limits) before Phase 9 (CRM
  push) ships, not after.
- **Scope**: this is a multi-quarter build. The phase table above is
  deliberately incremental so each phase ships something a BPO tenant can
  use, rather than accumulating unshippable infrastructure.
- **GitHub push still blocked** on `DYvixits/bpo-ai-scrap` (write access) —
  independent of this audit; let me know when it's resolved and I'll push
  the Phase 1–3 commits.

## 8. Open questions before Phase 1 (hardening) work starts

See the chat message accompanying this document.
