# Phase Plan

Built incrementally. Each phase must be functional before the next starts
(master spec §85, §103). This document is the standing reference for what
"done" means per phase, and is updated as phases land.

**Note:** the platform's product direction was revised mid-build toward
commercial intelligence for a BPO CRM — see
[`../AUDIT_BPO_CRM.md`](../AUDIT_BPO_CRM.md), whose §6 phase table (0–15,
approved reordering: CRM Integration ahead of Knowledge Graph) is now the
authoritative forward plan. This file's original 1–11 table is kept as-is
below for the Phase 1–3 history and verification reports; new phase work is
tracked against AUDIT_BPO_CRM.md's numbering instead of renumbering this one.

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

**NEXT (superseded)** — this originally said Phase 4 (Advanced Crawler); the
product direction changed before that started — see the note at the top of
this file and the Session 2 report immediately below, which covers what was
actually built next (multitenancy hardening) instead.

## Session 2 verification report — multitenancy hardening

Scope: `AUDIT_BPO_CRM.md`'s Phase 1 ("Foundation + multitenancy hardening"),
specifically tenant tiers/quotas and PostgreSQL Row-Level Security as
defense-in-depth on top of the app-layer tenant scoping Phase 1–3 already
had. Full design rationale lives in `SECURITY.md` §"Tenant isolation" and
`ARCHITECTURE.md` §4 — this section is the same implement→test→report
discipline as Session 1.

**IMPLEMENTED** — `organizations.tier` + `tenant_quotas` table (seeded from
tier defaults at signup, then an ordinary editable row per organization);
`organization_id` denormalized onto `research_events`/`sources`/
`crawl_pages`/`research_results`; PostgreSQL RLS (`ENABLE` + `FORCE ROW
LEVEL SECURITY` + a `tenant_isolation` policy) on those four tables plus
`tenant_quotas`; a SQLAlchemy `after_begin` listener
(`app/core/database.py::set_tenant_context`) that issues `SET LOCAL
app.current_tenant` on every transaction, wired from both
`app/core/deps.py::get_current_auth` (API requests) and
`app/workers/tasks/research.py` (background jobs); `max_concurrent_
research_jobs` quota enforcement on `POST /research` (HTTP 429 when
exceeded).

**TESTED** — 7 new automated tests: 2 quota-enforcement tests (SQLite —
pure app logic, no RLS needed) and 5 real-PostgreSQL RLS tests
(`tests/test_rls.py`, self-skipping without a reachable database, wired
into CI via a new `postgres:16-alpine` service container in
`.github/workflows/ci.yml`). 34/34 tests pass total. Also re-verified the
full register → login → create-research → live-pipeline flow end-to-end
against real Postgres + Redis + uvicorn + arq, the same way as Session 1.

**WORKING** — confirmed live, by hand, before the automated tests existed
to double-check them: an INSERT into an RLS-protected table with no tenant
context set is rejected; the same INSERT with the correct
`SET LOCAL app.current_tenant` succeeds; an INSERT claiming a different
organization than the active context is rejected; a `SELECT` from one
tenant's context never returns another tenant's rows, including with no
context set at all (fails closed, not open).

**Bugs found and fixed via real-Postgres testing (again, none of these are
visible to a SQLite-backed suite):**

1. **Enum insert failure carried over from Session 1's pattern, new
   instance.** Not applicable here — already fixed; noted only to say the
   `pg_enum()` fix held up under the new `tenant_tier` enum without
   incident.
2. **`SET LOCAL` cannot take a bind parameter.** PostgreSQL's grammar
   rejects `SET LOCAL x = $1` outright — a server-side restriction, not a
   driver bug. Fixed by validating the tenant id through `uuid.UUID(...)`
   (guaranteeing a safe 36-character canonical string with nothing to
   inject) and interpolating that into the SQL text directly, rather than
   binding it.
3. **RLS policy bootstrapping problem when creating a new organization.**
   `create_user_and_organization` inserts the new org's first
   `tenant_quotas` row before any tenant context exists for it (there's
   nothing to authenticate against — the org doesn't exist until this
   transaction). Fixed by generating the organization's UUID up front,
   calling `set_tenant_context` immediately, and forcing a fresh
   transaction (a harmless `commit()` — nothing was pending) so the
   `after_begin` listener actually re-fires with it, rather than applying
   too late to the transaction already opened by an earlier read in the
   same request.
4. **`current_setting(..., true)` doesn't reliably return `NULL`.** Only
   the very first time a session touches a given custom GUC. Once `SET
   LOCAL app.current_tenant` has been issued at least once on a pooled
   connection, a later transaction that forgets to set it again gets `''`
   back — and `''::uuid` raises a hard error rather than the policy
   evaluating to false. Fixed with `NULLIF(current_setting(...), '')::uuid`
   in every policy, so "no tenant context" fails closed consistently
   instead of erroring depending on connection reuse history.

Each of these is exactly the kind of bug that only a real database — not a
mock, not SQLite, not code review — surfaces, which is why this session
again prioritized running the actual stack over trusting the migration
file's SQL to be correct by inspection.

**REMAINING** — `research_jobs` itself is not RLS-protected (deliberate
scope boundary, documented in `SECURITY.md`; app-layer isolation there is
tested but not backstopped by RLS yet — closing that gap needs a
least-privilege worker role distinct from the request-serving role, tracked
for a later hardening pass, not silently dropped). Tenant tiers exist but
nothing yet reads/writes them beyond signup defaults (no admin console to
adjust a tenant's tier or quota — Phase 11 territory). `docker compose up`
still unverified in this sandbox (no Docker daemon) for the same reason as
Session 1.

**NEXT** — per `AUDIT_BPO_CRM.md`'s approved phase table: Phase 2 (Research
Orchestrator — NL→`ResearchObjective`, multi-query Search Strategy Engine,
multi-provider Source Discovery) or Phase 3 (Crawler Engine — adaptive
strategy, goal-driven prioritization), pending direction from whoever's
driving next.

## Session 3 verification report — Research Orchestrator (Query Intelligence + Search Strategy)

Scope: `AUDIT_BPO_CRM.md`'s Phase 2. A heuristic (non-LLM) Query
Intelligence Engine that parses the free-text research query into a
structured `ResearchObjective`, and a Search Strategy Engine that turns
that objective into multiple targeted search queries instead of searching
on the raw query alone. Full design rationale in `ARCHITECTURE.md` §1/§7 —
same implement→test→report discipline as Sessions 1–2.

**IMPLEMENTED** — `app/engines/query_intelligence/` (`objective.py`'s
`ResearchObjective` model, `keywords.py`'s curated geography/industry/
signal/attribute tables, `parser.py::parse_query` + `parse_result_limit`);
`app/engines/search_strategy/strategy.py::build_queries` (up to
`MAX_QUERIES=4` queries per objective); `research_jobs.objective` column
(migration `0003_research_objective.py`) populated once at job creation
by `research_orchestrator.py::create_and_enqueue` and never mutated after;
the worker (`workers/tasks/research.py`) now runs all of a job's queries
concurrently via `asyncio.gather`, then dedupes hits by URL before
crawling; the frontend's `ResearchDetailPage` renders the parsed objective
as "Understood as:" chips (industry, geography, company size, signals,
freshness, target entities) so a user can see how their query was
interpreted, with a tooltip pointing at `objective.matched_keywords` for
the literal evidence behind each chip.

**TESTED** — 20 new automated tests: 13 for `parse_query`/
`parse_result_limit` (`tests/test_query_intelligence.py`) and 7 for
`build_queries` (`tests/test_search_strategy.py`), all SQLite/pure-logic
(no database dependency — this engine touches no persistence itself).
54/54 tests pass total. Re-verified the full register → login →
create-research (with a query exercising industry, geography, company
size, signals, and a result-limit override) → live-pipeline → completed
flow end-to-end against real Postgres + Redis + uvicorn + arq, plus a
Playwright screenshot of the "Understood as:" chips rendering correctly
on the research detail page against the real Vite dev server.

**WORKING** — confirmed live: a query like "Find 250 fintech companies in
Cameroon with more than 50 employees that are currently hiring and
recently raised funding, including their CEO and revenue" parses into
`industry=[fintech], geography=[Cameroon], company_size_min=50,
signals=[hiring, funding], required_attributes=[ceo, revenue],
freshness=recent`, a `result_limit` override of 250 (capped at 50 by
`_MAX_RESULT_LIMIT_OVERRIDE`), and the Search Strategy Engine expands this
into multiple differently-worded queries rather than searching the raw
sentence verbatim.

**Bugs found and fixed via live testing against the running app (not
caught by the SQLite-backed unit tests written first):**

1. **Substring keyword-matching order bug.** `_match_keywords` iterated a
   canonical entry's surface forms in table-declaration order; several
   entries have one surface form that is a literal substring of another
   for the *same* canonical value (e.g. `"cameroon"` inside
   `"cameroonian"`), so the shorter, less specific form always matched
   first regardless of which one was actually in the text. Fixed by
   checking `sorted(surface_forms, key=len, reverse=True)` — longest
   candidate first.
2. **Missing keyword variant.** `"founding year"` (a completely ordinary
   phrasing) did not match the `founded_year` attribute — only `"founded"`
   and `"established"` were in the table. Added `"founding"` as a surface
   form.
3. **Result-limit regex too strict.** The original pattern required the
   number immediately adjacent to the noun (`\d+\s+companies`), which
   missed extremely common phrasing with an adjective in between — "250
   **fintech** companies" — entirely. This was only caught by manually
   exercising a realistic query against the live app; none of the unit
   tests written beforehand happened to include an adjective in that
   position. Fixed by allowing 0–2 filler words between the number and the
   noun, then added regression tests for both the fix and a negative case
   (`"250 people work at these growing companies"` → `None`, since 5
   filler words exceeds the cap and the number isn't actually a
   result-count in that sentence).

Each of these three is a case where the SQLite/unit-test suite, written
against the same assumptions as the implementation, could not have caught
the bug — only running the real parser against unscripted, realistic input
did. This is the same pattern Sessions 1–2 found with real-Postgres
testing, applied here to real-input testing instead.

**REMAINING** — the parser is a fixed curated keyword table (see
`keywords.py`) — it does not learn new geographies/industries/signals and
will silently produce an empty match for a term outside its tables (an
explicit design tradeoff for this phase: no LLM in the parsing path yet,
see `ARCHITECTURE.md` §7). `build_queries`' 4-query cap is a fixed
constant, not tuned against real search-provider result quality yet.
`docker compose up` still unverified in this sandbox (no Docker daemon),
same as Sessions 1–2.

**NEXT** — per `AUDIT_BPO_CRM.md`'s approved phase table: Phase 3 (Crawler
Engine — adaptive strategy, goal-driven prioritization) or the reordered
CRM Integration phase, pending direction from whoever's driving next.

## Session 4 verification report — Crawler Engine (link discovery + goal-driven prioritization)

Scope: `AUDIT_BPO_CRM.md`'s Phase 3 — the "adaptive strategy, goal-driven
prioritization" half of it (NextBestURL scoring, information-gain early
stopping, same-domain link discovery). Playwright/JS-rendering, sitemap/
RSS/JSON-LD/PDF handling, and multi-provider source discovery remain
unstarted — see REMAINING below. Full design rationale in
`ARCHITECTURE.md` §1/§7 — same implement→test→report discipline as
Sessions 1–3.

**IMPLEMENTED** — `app/engines/crawler/links.py::extract_links` (same-
registrable-domain link discovery from a fetched page's HTML, fragment-
stripped and deduplicated, filtering out mailto/tel/javascript links and
common asset extensions); `app/engines/crawler/prioritization.py`
(`score_candidate` — NextBestURL scoring against the objective's
`required_attributes` via a new `ATTRIBUTE_PAGE_SIGNALS` keyword table,
decayed by crawl depth; `InformationGainTracker` — reuses the Query
Intelligence Engine's own `ATTRIBUTES` table to detect, per page, which
required attributes were actually found). The worker
(`workers/tasks/research.py`) no longer fetches a flat batch of search
hits — it runs a priority frontier (a heap scored by `score_candidate`),
crawling wave-by-wave up to a new `max_pages` config field (distinct from
`max_results`, which now only sizes the search-hit seed set), expanding
the frontier with each page's discovered links, and stopping early either
once every required attribute is found (`objective_satisfied`) or after a
run of pages that found nothing new (`diminishing_returns`, gated by
`_STALL_LIMIT`/`_STALL_FLOOR` so a couple of unlucky early picks can't end
a job prematurely). Two new WebSocket/event kinds, `crawl.expanded` and
`crawl.stopped_early`, report this — see `docs/API.md`. `MODE_DEFAULTS`
gained a `max_pages` per mode; the query-text result-limit override (e.g.
"find 500 companies") now raises `max_pages` alongside `max_results`,
closing the gap flagged in Session 1's `_MAX_RESULT_LIMIT_OVERRIDE`
comment ("revisit once goal-driven prioritization makes 'more results' a
budget decision").

**TESTED** — 27 new automated tests, all SQLite/pure-logic except where
noted: 9 for `extract_links` (`tests/test_links.py`), 9 for
`score_candidate`/`InformationGainTracker` (`tests/test_prioritization.py`),
and 3 full worker-pipeline tests with the network layer stubbed exactly
like Session 1's `test_research_pipeline.py`
(`tests/test_crawl_prioritization_pipeline.py`): one proves the crawler
actually follows a same-domain link to find a required attribute the seed
page didn't have, one proves a crawl stops the instant the objective is
satisfied (a discovered-but-unnecessary page is never fetched), one proves
a crawl stops on diminishing returns before exhausting a 6-page budget
(forcing `crawler_max_concurrency=1` via monkeypatch so the stall counter
is checked at page-level granularity, not wave-level). 75/75 tests pass
total, including all 5 real-Postgres RLS tests re-run against a real local
Postgres 16 with the same non-superuser `bpo_app` role introduced by the
RLS least-privilege CI fix (a between-sessions fix, not numbered above —
see SECURITY.md's "Tenant isolation" section and its own PR for that
one) — specifically to check that the frontier loop's many more per-page
`_tenant_session` transactions (one wave can now open several in quick
succession) didn't regress RLS enforcement. They didn't.

**WORKING** — confirmed via the pipeline tests above, which exercise the
real frontier/scoring/tracking code end-to-end (only the network calls are
stubbed): a company homepage that doesn't mention its CEO but links to
`/about`, which does, gets both pages crawled; a homepage that already
answers the objective on its own never triggers a crawl of the `/team`
page it links to; six equally-uninformative candidate pages stop being
crawled after 3, not 6. A **live** end-to-end run against a real external
site was not possible this session — the sandbox's egress policy blocks
general outbound HTTPS, not just the DuckDuckGo host flagged in Session 1
(confirmed directly: a plain `httpx` request to `https://example.com`
returns `403 Forbidden` from the environment's own proxy) — so this
phase's "real infrastructure" testing takes the same shape Session 1's
pipeline test already established for exactly this constraint: real DB,
real event log, real scoring/tracking logic, stubbed network boundary.

**REMAINING** — everything else `AUDIT_BPO_CRM.md`'s Phase 3 scopes:
adaptive strategy selection (a Playwright-backed fetcher for JS-heavy
pages, chosen per URL — `PageFetcher` stays HTTP-only), sitemap/RSS/
JSON-LD/PDF discovery, and multi-provider source discovery (still
DuckDuckGo-only, a Phase 2 item that was never closed either).
`ATTRIBUTE_PAGE_SIGNALS` is a small curated table like every other
keyword table in this codebase — modest, not exhaustive, and it will
silently score a company site with unconventional page naming no higher
than the baseline. `docker compose up` still unverified in this sandbox
(no Docker daemon), same as every prior session.

**NEXT** — per `AUDIT_BPO_CRM.md`'s approved phase table: the rest of
Phase 3 (adaptive fetcher, multi-provider discovery) or Phase 4
(Extraction + Deduplication — multi-pass extraction, 6-level dedup),
pending direction from whoever's driving next.

## Session 5 verification report — Extraction + Deduplication

Scope: `AUDIT_BPO_CRM.md`'s Phase 4. The audit's original phrasing calls
for "6-level dedup" without specifying what the six levels are anywhere in
this codebase's own docs — rather than invent six to match the label, this
session implements and honestly documents three real, tested layers, and
says plainly in REMAINING below that the "6-level" framing isn't something
this repo has ever concretely defined. Same implement→test→report
discipline as Sessions 1–4.

**IMPLEMENTED** — A second extraction pass,
`app/engines/extraction/structured.py::extract_structured_data`, alongside
trafilatura's existing main-content text pass: parses JSON-LD
(`schema.org`) blocks, Open Graph / meta description tags, and plain-text
email/phone matches — every field either literally present in the markup
or a direct regex match, nothing inferred. Stored on a new
`crawl_pages.structured_data` JSON column (migration `0004`). Three dedup
layers, in the order they're checked: (1) `app/engines/crawler/
normalize.py::normalize_url` — strips tracking params (`utm_*`, `fbclid`,
`gclid`, ...), sorts remaining query params, strips trailing slashes and
fragments; used as the crawl frontier's dedup key at push time, so a
tracking-param variant of an already-queued URL never occupies a frontier
slot. (2) The existing exact content-hash match (unchanged from Phase
1–3). (3) `app/engines/extraction/dedup.py::NearDuplicateDetector` — new:
shingles each page's text into overlapping 5-word sequences and flags a
page as a near-duplicate once its Jaccard similarity to any already-seen
page in the same job crosses 0.9. A duplicate by either (2) or (3) is
still crawled and recorded (`crawl_pages` row, `structured_data` and all)
— only the `research_results` row is skipped, and `page.completed`'s new
`duplicate_reason` field says which layer caught it. See `docs/API.md`.

**TESTED** — 46 new tests, all SQLite/pure-logic except the pipeline
tests: 9 for `normalize_url`, 9 for `extract_structured_data`
(`tests/test_structured_extraction.py`), 10 for shingling/Jaccard/
`NearDuplicateDetector` (`tests/test_dedup.py`), and 3 full worker-pipeline
tests with the network layer stubbed (`tests/test_extraction_dedup_
pipeline.py`) proving a tracking-param link to the seed page is never
separately crawled, a near-duplicate `/print` page is crawled but
produces no second result, and `structured_data` from real JSON-LD/meta
tags lands on the stored `crawl_pages` row. 106/106 backend tests pass
total, including all 5 real-Postgres RLS tests re-verified against the
`0004` migration and the `bpo_app` least-privilege role.

**WORKING** — confirmed via the pipeline tests above (real DB writes,
real scoring/extraction/dedup logic, only network stubbed — the same
constraint as every prior session: this sandbox's egress policy blocks
general outbound HTTPS, not just the previously-documented DuckDuckGo
host, so no live external crawl is possible here). One real bug was
found while writing these tests, not by them: Phase 3's own
`test_pipeline_stops_on_diminishing_returns_before_exhausting_budget`
used byte-identical filler text across all six candidate pages, so once
near-duplicate detection existed, pages 2–6 correctly started being
flagged as near-duplicates of page 1 — that test's assertion ("every
crawled page yields a result") had been quietly relying on the fixture
never having realistic duplicate content. Fixed the fixture to use
distinct text per page, since that test's actual purpose is the
stall/early-stop logic, not dedup — the new dedup behavior itself is
correct and is exactly what a later session's tests now cover directly.

**REMAINING** — Only 3 dedup layers exist, not the "6-level dedup" the
audit's phase-table label names; that number was never broken down
anywhere in this repo's docs, so nothing was silently skipped — it's
flagged here as a label the codebase doesn't yet substantiate, for
whoever defines the other 3 next (candidates per the master spec's
broader intent: entity-level dedup once Phase 5 Entity Resolution exists,
cross-source/cross-job dedup, and structural/DOM-based similarity beyond
plain text shingling). `ATTRIBUTE_PAGE_SIGNALS`/`ATTRIBUTES` still don't
extract `structured_data`'s fields into `required_attributes` satisfaction
— `InformationGainTracker` still only looks at trafilatura's plain text,
so a page with a CEO's name *only* in JSON-LD and not in visible prose
wouldn't count as satisfying that attribute yet. `docker compose up` still
unverified in this sandbox (no Docker daemon), same as every prior
session.

**NEXT** — per `AUDIT_BPO_CRM.md`'s approved phase table: Phase 5 (Entity
Resolution) is the next unstarted phase in sequence, or the still-open
remainders of Phase 2 (multi-provider source discovery) and Phase 3
(adaptive fetcher), pending direction from whoever's driving next.

## Session 6 verification report — Entity Resolution

Scope: `AUDIT_BPO_CRM.md`'s Phase 5. Same implement→test→report discipline
as Sessions 1–5.

**IMPLEMENTED** — `app/engines/entity_resolution/resolver.py::
resolve_companies`, a disclosed two-step heuristic (no ML, no fuzzy string
similarity beyond exact match on a normalized name): (1) pages are grouped
by registrable domain — already correct by construction, since the
crawler only follows same-domain links (`crawler/links.py`); (2)
domain-groups are merged into one company when their best-guess names —
read from JSON-LD `Organization`/`LocalBusiness`, then Open Graph site
name, then the first segment of the OG title or page title, in that
preference order (the same "most structured signal first" pattern as
`extraction/structured.py`) — are identical after normalization
(lowercased, legal-suffix-stripped e.g. "Inc"/"Ltd"/"GmbH", punctuation-
stripped). New tables `companies` and `entity_aliases` (migration `0005`,
RLS enabled with the same `tenant_isolation` policy as migration `0002`'s
tables) plus a nullable `research_results.company_id` FK. The resolver
runs once per job in `app/workers/tasks/research.py`, after the crawl loop
ends and before `EXTRACTING`/`COMPLETED`, reading every successfully
fetched `crawl_pages` row for the job. `match_confidence` is `1.0` for an
unmerged single-domain company (nothing to disambiguate) and `0.7` for a
cross-domain name-match merge — a disclosed number, not a verified claim
(SECURITY.md). New `GET /research/{id}/companies` endpoint and
`entities.resolved` WS/event-log event (`{"count": N}`). Frontend: results
on `ResearchDetailPage` are now grouped under a `CompanyGroup` header
(canonical name, description, and a "N sources merged · X% match
confidence" badge shown only when more than one domain was merged);
ungrouped results (no resolvable name) render under a plain "Not grouped
into a company" label instead of disappearing or crashing.

**TESTED** — 15 new tests: 12 pure-logic unit tests for the resolver
(`tests/test_entity_resolution.py` — name normalization, JSON-LD/OG/title
fallback priority, single-domain grouping, cross-domain merge on matching
names, no-merge on different names, alias recording, empty input) and 3
full worker-pipeline tests with the network layer stubbed
(`tests/test_entity_resolution_pipeline.py` — same-domain pages resolve
into one company at confidence 1.0, two different domains with matching
site names merge at confidence 0.7, zero search hits produce zero
companies). Plus 2 new API tests (`tests/test_research.py` —
`/companies` is empty before the pipeline runs, 404s for an unknown job,
and is included in the existing cross-tenant-isolation test alongside
`/results`). 118/118 backend tests pass on SQLite (5 skipped —
Postgres-only RLS tests); 123/123 pass against a real local PostgreSQL
with migrations `0001`–`0005` applied and the suite pointed at the
non-superuser `bpo_app` role (mirroring CI's least-privilege setup, see
SECURITY.md) — i.e. every Entity Resolution write in the pipeline tests
genuinely went through RLS enforcement on `companies`/`entity_aliases`,
not just SQLite with RLS structurally absent. No dedicated per-table RLS
unit test was added for the two new tables: `tests/test_rls.py` exercises
the fail-closed/correct-context/wrong-context/select-scoping behavior
against one representative table (`research_events`), and `companies`/
`entity_aliases` reuse that exact same policy DDL, verbatim, from
migration `0002` — the pipeline tests passing under `bpo_app` is the
integration-level evidence that the policy actually applies to them, not
just that the DDL ran without error. Frontend: `npm run build` and
`npm run lint` both clean (the two pre-existing Fast-Refresh warnings in
`badge.tsx`/`button.tsx` predate this session).

**WORKING** — confirmed via the pipeline tests (real DB writes, real
resolver logic, only network stubbed — same sandbox egress constraint as
every prior session) **and** a live visual check: seeded a `COMPLETED`
research job directly via the app's own SQLAlchemy models (a real search→
crawl run isn't reachable in this sandbox) with one single-domain company,
one two-domain merged company, and one ungrouped result, then loaded
`ResearchDetailPage` in a real Chromium browser (Playwright) against a
running FastAPI + Vite dev stack. The screenshot caught a real, if minor,
layout bug the pipeline/unit tests couldn't: the company header's name,
badge, and description shared one `flex items-center` row with no wrap,
so a company with a two-word name and a description pushed the badge and
description apart with an ugly gap. Fixed by wrapping the name/badge onto
their own flex-wrap row and moving the description to its own line below
— same category of bug the Session 1 frontend event-timeline fix caught,
confirming visual verification still earns its cost here.

**REMAINING** — Resolution only covers companies; the master spec's
person-entity resolution (same person across pages/sources) is out of
scope for this session. The name-match merge step is a strict exact-match
on normalized text — two real variants that don't reduce to the same
normalized string (e.g. an abbreviation or a rebrand) will not merge; this
is a deliberate false-splits-over-false-merges tradeoff (see the
resolver's module docstring), not an oversight, but it means recall on
cross-domain merges is conservative. `Company`/`EntityAlias` are scoped
per `research_job`, not deduplicated across a tenant's jobs or over time —
the same company researched twice produces two separate `Company` rows.
No confidence value between 0.7 and 1.0 exists yet (e.g. a 3+-domain merge
isn't scored any differently from a 2-domain one) — flagged here rather
than inventing a formula this session can't substantiate.

**NEXT** — per `AUDIT_BPO_CRM.md`'s approved phase table: Phase 6
(Verification + Evidence) is the next unstarted phase in sequence, or the
still-open remainders of Phase 2 (multi-provider source discovery) and
Phase 3 (adaptive Playwright-based fetcher), pending direction from
whoever's driving next.

## Session 7 verification report — Verification Engine

Scope: `AUDIT_BPO_CRM.md`'s Phase 6. The master spec's Phase 6 asks for a
lot: multi-source corroboration, an Evidence Engine linking every *claim*
to its source excerpt, a Contradiction Engine, and a 7-state Truth Engine
(`VERIFIED, CORROBORATED, PROBABLE, UNCERTAIN, CONTRADICTED, OUTDATED,
UNVERIFIABLE`). None of that is reachable honestly in one session, because
it all assumes claim extraction (structured subject–predicate–object
facts, e.g. "founded_year: 2021") — and claim extraction was never built
in this codebase; `AUDIT_BPO_CRM.md`'s own services table still lists
"Evidence Engine — MISSING — no Claim/Evidence tables yet" as of the start
of this session. Rather than fabricate claim-level agreement/contradiction
detection this repo has no data to support, this session builds
verification one level up — at the company/source level, using only real
signals Entity Resolution already produces — and says plainly below
exactly which 5 of the 7 Truth Engine states are actually computed and
why the other 2 aren't. Same implement→test→report discipline as
Sessions 1–6.

**IMPLEMENTED** — `app/engines/verification/engine.py::compute_confidence`:
for each resolved Company, gathers its crawled pages as `EvidenceInput`
(domain, source_url, excerpt, crawled_at) and computes `source_count`
(pages), `source_diversity` (distinct domains — a domain only counts once
no matter how many of its pages resolved to this company),
`freshness_score` (1.0 within a 30-day grace period, decaying linearly to
0 by `OUTDATED_DAYS` = 180, using whichever piece of evidence is
freshest), and `evidence_completeness` (fraction of evidence entries that
actually carry a non-blank excerpt). `status` is one of `UNVERIFIABLE` (no
evidence), `UNCERTAIN` (1 domain), `CORROBORATED` (2 domains), `VERIFIED`
(≥3 domains, per master spec §98's "≥3 independent sources" rule), or
`OUTDATED` (freshest evidence older than `OUTDATED_DAYS`, which overrides
diversity — stale evidence from 5 domains is still stale).
`PROBABLE`/`CONTRADICTED` are not computed — both need to compare what
different sources actually *claim*, and this phase doesn't build claim
extraction to make that comparison possible. New tables: `evidence` (one
row per crawled page counted toward a company's score — page-level, not
claim-level) and `confidence_scores` (one row per company, migration
`0006`, RLS via the same `tenant_isolation` policy as every prior
per-job table). Runs once per company in `app/workers/tasks/research.py`,
immediately after Entity Resolution writes it — same wave, same
transaction pattern. New `entities.resolved`-sibling event
`verification.completed` (`{"counts": {...}}`), and `GET /research/{id}/
companies` now returns each company's `confidence_score` and `evidence`
inline (`app/schemas/entity.py::CompanyOut`, eager-loaded via
`entity_repository.list_companies_for_job`'s `selectinload`).

Frontend: `CompanyGroup`'s header gains a `VerificationBadge` (green
"Verified", blue "Corroborated", amber "Uncertain", outline "Outdated" —
color follows the same success/warning/outline vocabulary as `ResultCard`'s
confidence badge) with a tooltip disclosing the source count/diversity
behind it, and a "View evidence (N)" disclosure listing each contributing
domain, link, and excerpt — same collapsed-by-default pattern as
`ResultCard`'s "Why this score?".

**TESTED** — 26 new tests: 10 pure-logic unit tests for
`compute_confidence` (`tests/test_verification_engine.py` — every status
transition, same-domain pages not counting as diversity, one fresh source
among stale ones avoiding `OUTDATED`, evidence-completeness with
missing/blank excerpts, the freshness decay curve), 3 full worker-pipeline
tests with the network layer stubbed (`tests/test_verification_pipeline.py`
— a single-domain company lands `UNCERTAIN`, a 3-domain merge lands
`VERIFIED` with the right evidence rows, zero companies means zero
confidence_scores rows), 1 API-layer test
(`tests/test_research.py::test_companies_response_includes_verification_
and_evidence` — hits `GET /research/{id}/companies` through the real
FastAPI/httpx client and checks the nested `confidence_score`/`evidence`
JSON actually serializes from the ORM relationships, which the
pipeline tests querying the DB directly don't exercise). 132/132 backend
tests pass on SQLite (5 skipped — Postgres-only RLS tests); 137/137 pass
against a real local PostgreSQL with migrations `0001`–`0006` applied,
pointed at the non-superuser `bpo_app` role — every Verification Engine
write in the pipeline tests went through real RLS enforcement on
`evidence`/`confidence_scores`, and the `0006` migration's upgrade/
downgrade/upgrade cycle was exercised directly. Backend `ruff check`/
`ruff format` and frontend `npm run build`/`npm run lint` both clean
(same 2 pre-existing Fast-Refresh warnings as every prior session).

**WORKING** — confirmed via the pipeline/API tests (real DB writes, real
scoring logic, only network stubbed — same sandbox constraint as every
prior session) **and** a live visual check: seeded a `COMPLETED` research
job directly via the app's SQLAlchemy models with 4 companies, one for
each computed status (`VERIFIED`/`CORROBORATED`/`UNCERTAIN`/`OUTDATED`),
then loaded `ResearchDetailPage` in a real Chromium browser via
Playwright. All 4 badges render with visually distinct colors, tooltips
show the right source-count language, and the evidence disclosure expands
to show domain/link/excerpt per source. One real bug was found this way,
not by the pipeline tests: SQLite silently returns a *naive* datetime for
a `DateTime(timezone=True)` column on read-back (unlike Postgres, which
preserves the tzinfo), so `compute_confidence`'s `now - crawled_at`
subtraction raised `TypeError: can't subtract offset-naive and
offset-aware datetimes` the moment a real crawled page (not a hand-built
test fixture) was passed through the pipeline — caught immediately by
`test_verification_pipeline.py`, not the live check, but it's the same
category of "a hand-rolled unit-test fixture didn't hit a real
cross-dialect gap" bug this project has hit before (see Session 5's dedup
fixture bug). Fixed with a `_age_days()` helper that treats a naive
timestamp as UTC before subtracting, on both sides, so the same code path
is correct whether the value came from SQLite or Postgres.

**REMAINING** — No claim-level verification: this phase's `status` and
`evidence` are about *pages*, not about whether the specific facts on
those pages agree with each other. `PROBABLE` and `CONTRADICTED` are not
computed, and won't be until a claim extraction engine exists to give
them something to compare. "Independent domain" is a proxy for
independent sourcing, not a verified one — two syndicated copies of the
same press release on two different domains still count as 2 sources
today, which is a real, disclosed limitation, not an oversight.
`confidence_scores` is scoped per `research_job`, like `companies` — a
company re-researched in a later job gets a fresh, unrelated score, not
an updated one. Freshness is computed once, at pipeline-completion time,
so it's nearly always 1.0 for a job that just finished; `OUTDATED` only
becomes meaningful once a company's evidence is read back long after the
job ran, or (Phase 10 Monitoring) a job is re-run against the same
company later. `research_results.confidence` (the Phase 1–3 per-page
"basic relevance score") is deliberately *not* retired despite
`AUDIT_BPO_CRM.md`'s phase-table wording — it's kept, unchanged, as a
lower-level, already-honestly-labeled signal ("basic relevance score, not
verified") for individual results, including the ones that never get
grouped into a company at all; `confidence_scores` is a new, separate,
company-level signal layered on top, not a replacement, because retiring
the column wholesale would need per-result claim-level confidence this
phase has no data to compute.

**NEXT** — per `AUDIT_BPO_CRM.md`'s approved phase table: Phase 7
(Commercial Signals + Temporal Decay) is the next unstarted phase in
sequence, or the still-open remainders of Phase 2 (multi-provider source
discovery) and Phase 3 (adaptive Playwright-based fetcher), pending
direction from whoever's driving next.

## Session 8 verification report — Commercial Signal Engine

Scope: `AUDIT_BPO_CRM.md`'s Phase 7 (Commercial Signals + Temporal
Decay). Same implement→test→report discipline as Sessions 1–7.

**IMPLEMENTED** — `app/engines/commercial_signals/detector.py::
detect_signals`: scans a resolved company's own crawled page text for the
same disclosed keyword vocabulary `query_intelligence/keywords.py::
SIGNALS` already uses to parse the user's *query* — that dict's own
comment had flagged it as "recorded now so [Phase 7's Commercial Signal
Engine] has a documented starting vocabulary," so this session reuses it
rather than inventing a parallel keyword table (9 types: `hiring,
expansion, funding, acquisition, leadership_change, product_launch,
digital_transformation, layoffs, closure`, each already carrying a
`positive`/`negative` polarity). At most one signal per type per page
(first matching surface form wins, same simplicity as entity_resolution's
name selection), with a bounded excerpt around the match. Temporal decay:
`decay_strength` fades a signal's `base_weight` — deliberately uniform
`1.0` across every type, since per-type weighting is a scoring decision
that belongs to Phase 8's Intent Engine, not this phase — linearly to `0`
over `SIGNAL_DECAY_DAYS` (180, matching Verification's `OUTDATED_DAYS` for
consistency), anchored to the source page's crawl time. No real event
date is extracted from page prose — that's a much harder, error-prone NLP
problem than keyword matching, and this phase doesn't attempt it, the
same disclosed limitation Verification already carries for evidence
freshness. New `commercial_signals` table (migration `0007`, RLS via the
same `tenant_isolation` policy as every prior per-job table), one row per
detected (company, page, signal_type). Runs once per company in
`workers/tasks/research.py`, immediately after Verification writes its
score — same wave, same transaction. New `signals.detected` event
(`{"counts": {...}}`), fired only if at least one signal was found
anywhere in the job (unlike `entities.resolved`/`verification.completed`,
a job can complete with real companies and zero signals). `GET
/research/{id}/companies` now returns each company's `signals` inline.

Frontend: `CompanyGroup` gains a `SignalChips` row — one badge per
distinct signal type found (deduplicated to the strongest instance across
the company's pages), colored by polarity (secondary for positive,
warning for negative), with a tooltip disclosing the matched keyword,
excerpt, and current decayed strength.

**TESTED** — 22 new tests: 12 pure-logic unit tests for the detector
(`tests/test_commercial_signals.py` — the `CommercialSignalType` enum
stays in sync with `SIGNALS`' keys, case-insensitive matching, multiple
distinct types on one page, at-most-one-per-type, excerpt bounding,
polarity carried through, decay at zero/midpoint/past-the-window ages,
decay handles naive datetimes without raising), 2 full worker-pipeline
tests with the network layer stubbed (`tests/test_commercial_signals_
pipeline.py` — a page mentioning a funding round produces exactly one
`funding` `CommercialSignal` row at full decayed strength; generic
content with no signal keywords produces zero rows and no
`signals.detected` event), and the existing API-layer test in
`tests/test_research.py` was extended (not duplicated) to assert
`signals` serializes correctly through `GET /research/{id}/companies`.
146/146 backend tests pass on SQLite (5 skipped — Postgres-only RLS
tests); 151/151 pass against a real local PostgreSQL with migrations
`0001`–`0007` applied, pointed at the non-superuser `bpo_app` role — every
Commercial Signal write in the pipeline tests went through real RLS
enforcement on `commercial_signals`, and the `0007` migration's
upgrade/downgrade/upgrade cycle was exercised directly. Backend `ruff
check`/`ruff format` and frontend `npm run build`/`npm run lint` both
clean (same 2 pre-existing Fast-Refresh warnings as every prior session).

**WORKING** — confirmed via the pipeline/API tests (real DB writes, real
detection/decay logic, only network stubbed — same sandbox constraint as
every prior session) **and** a live visual check: seeded a `COMPLETED`
research job directly via the app's SQLAlchemy models with one company
carrying three positive signals (funding, hiring, expansion) and one
company carrying a negative signal (layoffs), then loaded
`ResearchDetailPage` in a real Chromium browser via Playwright. Both
polarity colors rendered correctly and each chip's label matched its
signal type; no bugs were caught by the live check this session (the
pipeline tests had already caught the one real bug — see below — before
the visual pass even ran).

One real bug was found, by the pipeline tests, not by hand-inspection:
the first draft of `decay_strength` subtracted `now - crawled_at`
directly, and the very first pipeline test (a real crawled page, not a
hand-built fixture) raised `TypeError: can't subtract offset-naive and
offset-aware datetimes` — the same SQLite-vs-Postgres tzinfo gap Session
7's Verification Engine hit and documented (SQLite silently drops tzinfo
from a `DateTime(timezone=True)` column on read-back). Rather than import
Verification's private `_age_days` helper across engines, this session
duplicates a two-line equivalent locally in `commercial_signals/
detector.py`, with a comment explaining why the duplication is
deliberate: the two engines are otherwise decoupled by design (see
ARCHITECTURE.md's engine-per-concern layout), and a shared cross-engine
utility module felt like more coupling than a 4-line fix warranted.

**REMAINING** — No real event-date extraction: `decayed_strength` reflects
"how recently we crawled a page mentioning this," not "how recently the
event actually happened" — a funding round from a year ago still decays
as if detected today, if the press release stays on the page and gets
re-crawled. `base_weight` is uniform across all 9 signal types; nothing
in this phase judges "funding" as more or less important than "hiring"
for any given tenant's sales motion — intentional, since per-tenant
weighting is Phase 8's Intent Engine / master spec §56's Configuration
Engine's job. `decayed_strength` is computed once, at pipeline-completion
time, same non-live-updating limitation as `confidence_scores` (see
Session 7's report) — it doesn't keep decaying in the database as real
time passes without a future re-run (Phase 10 Monitoring). Detection is
purely lexical: a page that describes a funding round without using any
of the `SIGNALS` dict's literal surface forms produces no signal — this
is the same recall-vs-precision tradeoff every keyword-table engine in
this codebase already discloses (query_intelligence, crawler
prioritization).

**NEXT** — per `AUDIT_BPO_CRM.md`'s approved phase table: Phase 8 (Fit +
Intent + Opportunity Scoring — the master spec's explicit
FIT/INTENT/CONFIDENCE-as-separate-tables architecture, §4) is the next
unstarted phase in sequence, and now has real `confidence_scores` and
`commercial_signals` rows to build `intent_scores`'
`contributing_signals[]` from — or the still-open remainders of Phase 2
(multi-provider source discovery) and Phase 3 (adaptive Playwright-based
fetcher), pending direction from whoever's driving next.

## Session 9 verification report — Fit / Intent / Opportunity Scoring

Scope: `AUDIT_BPO_CRM.md`'s Phase 8 (Fit + Intent + Opportunity Scoring —
master spec §4's explicit "do not blend FIT/INTENT/CONFIDENCE into one
number" architecture, confirmed as this project's highest-leverage design
decision back in the original audit). Same implement→test→report
discipline as Sessions 1–8.

**IMPLEMENTED** — Three new engines, run once per resolved company,
immediately after Verification and Commercial Signals in the same
worker loop:

- `app/engines/fit_scoring/engine.py::compute_fit` — checks a company's
  combined crawled-page text against the query's `industry`/`geography`/
  `required_attributes`, reusing the exact `INDUSTRY`/`GEOGRAPHY`/
  `ATTRIBUTES` keyword tables Query Intelligence used to parse those
  criteria out of the query in the first place — the same "one
  vocabulary, spent both ways" pattern `crawler/prioritization.py::
  InformationGainTracker` already established for `required_attributes`,
  now extended to industry/geography and moved from "did the crawl find
  this anywhere" to "does this specific company's own evidence show
  this." `score` is `matched / (matched + unmatched)`; `None`, not `0.0`,
  when the objective declared zero checkable criteria — nothing to
  compute fit against, so a number would be fabricated. Not scored:
  `company_size_min`/`max` (no headcount data is ever extracted from
  crawled pages anywhere in this codebase).
- `app/engines/intent_scoring/engine.py::compute_intent` — averages
  `decayed_strength` across a company's `commercial_signals` rows,
  unweighted by polarity (a funding round and a round of layoffs both
  mean something is *changing*, and deciding one is "better" for a given
  tenant's pitch is a judgment this phase deliberately doesn't make, same
  reasoning `commercial_signals/detector.py` gives for its own uniform
  `base_weight`). `0.0`, not `None`, when a company has zero signals —
  "nothing happening" is itself a real, computed answer.
- `app/engines/opportunity_scoring/engine.py::compute_opportunity` —
  master spec §4's `OPPORTUNITY = f(FIT, INTENT, CONFIDENCE, FRESHNESS,
  MOMENTUM)`. `f` is one fixed, disclosed weighted average
  (`DEFAULT_WEIGHTS`: fit 0.3, intent 0.3, confidence 0.2, freshness 0.1,
  momentum 0.1) — not yet the per-tenant-configurable function the spec
  actually asks for (that needs §56's Configuration Engine, still
  MISSING) — but every row stores the `weights_used` that produced it, so
  swapping in real per-tenant weights later is a data change, not a
  schema change. A `None` Fit score becomes a neutral `0.5` component
  rather than being dropped from the sum, so it never silently reweights
  the other four dimensions. `momentum` (`compute_momentum`) is the
  fraction of a company's signals that are `positive` polarity — a
  same-snapshot proxy, not a real trend/velocity metric, disclosed as
  such (see REMAINING).

New tables `fit_scores`, `intent_scores`, `opportunity_scores` (migration
`0008`, RLS via the same `tenant_isolation` policy as every prior per-job
table; `opportunity_scores` FKs to all three of `fit_scores`/
`intent_scores`/`confidence_scores` so "Why This Lead" is a join over
real rows, not a recomputation). `GET /research/{id}/companies` now
returns `fit_score`/`intent_score`/`opportunity_score` inline. New
`scoring.completed` event (`{"count": N, "average_opportunity_score":
..., "top_opportunity_score": ...}`), fired unconditionally alongside
`entities.resolved` — every resolved company always gets all three
scores, unlike Commercial Signals which can legitimately find nothing.

Frontend: `CompanyGroup` gets a prominent `OpportunityBadge` (green ≥70%,
amber ≥40%, outline below — same banding language as `ResultCard`'s
confidence badge) placed first in the header, with a tooltip breaking
down every weighted component and its weight. Companies are now sorted
by Opportunity Score descending (ties broken by the existing
most-consolidated-first rule) instead of purely by consolidation — the
whole point of this score, per the master spec, is surfacing the best
leads first.

**TESTED** — 25 new tests: 20 pure-logic unit tests across the three
engines (`tests/test_fit_scoring.py`, `test_intent_scoring.py`,
`test_opportunity_scoring.py` — no-criteria `None` fit, case-insensitive
matching, partial multi-criterion fit, zero-signal intent, negative-
polarity signals still contributing to the intent score, all-zero/all-max
opportunity inputs, `None` fit falling back to the neutral default,
custom weights being respected, momentum as a fraction of positive
signals), 2 full worker-pipeline tests with the network layer stubbed
(`tests/test_scoring_pipeline.py` — a fintech-mentioning page produces
`fit.score == 1.0` and a real `funding` contributing signal; a
criteria-free query produces `fit.score is None` and an opportunity row
whose `fit_component` correctly falls back to `0.5`), and the existing
API-layer test in `tests/test_research.py` was extended (not duplicated)
to assert `fit_score`/`intent_score`/`opportunity_score` all serialize
correctly through `GET /research/{id}/companies`. 168/168 backend tests
pass on SQLite (5 skipped — Postgres-only RLS tests); 173/173 pass
against a real local PostgreSQL with migrations `0001`–`0008` applied,
pointed at the non-superuser `bpo_app` role — every Fit/Intent/
Opportunity write in the pipeline tests went through real RLS
enforcement on the three new tables, and the `0008` migration's
upgrade/downgrade/upgrade cycle was exercised directly. Backend `ruff
check`/`ruff format` and frontend `npm run build`/`npm run lint` both
clean (same 2 pre-existing Fast-Refresh warnings as every prior session).

**WORKING** — confirmed via the pipeline/API tests (real DB writes, real
scoring logic, only network stubbed — same sandbox constraint as every
prior session) **and** a live visual check that, unlike every prior
session's, seeded data by running the *real* worker pipeline against
real Postgres (via `unittest.mock.patch` on the search/fetch providers,
the same technique the pytest suite uses) rather than hand-building ORM
rows — a stronger check for a phase whose new tables carry three
different foreign keys apiece, where a hand-seeded row could easily hide
a real FK-wiring bug the actual code path wouldn't. Three companies
(high/medium/low expected opportunity) were resolved, scored, and
rendered in a real Chromium browser via Playwright: badges showed 96%
(green), 41% (amber), and 26% (outline) respectively, in that sorted
order, and the "Signals:" row appeared only on the company whose page
text actually matched a signal keyword — confirming both the color
banding and the new sort-by-opportunity behavior work end to end. No
bugs were found this session, by either the pipeline tests or the live
check — the first implementation ran clean, likely because Sessions 7
and 8's `_age_days`-style tzinfo fix was applied proactively in
`fit_scoring`/`intent_scoring`/`opportunity_scoring` from the start
rather than being discovered by a failing test (these three engines
don't handle datetimes directly at all, sidestepping that whole class of
bug by construction).

**REMAINING** — `f` in `OPPORTUNITY = f(...)` is a single fixed default
weighting for every tenant, not the per-tenant-configurable function
master spec §4/§56 actually specifies — that needs a Configuration Engine
this codebase doesn't have yet. `momentum` is a same-snapshot proxy
(fraction of positive-polarity signals in this one job), not a measured
trend — real momentum needs the same company observed across multiple
jobs over time, and `companies`/`commercial_signals`/the new scoring
tables are all scoped per `research_job`, not tracked across repeated
research on the same company (the same limitation Phase 5's and Phase
7's REMAINING sections already flagged; Phase 10 Monitoring's job, not
this one's). Fit Scoring only checks three of the objective's fields —
`company_size_min`/`max` are never assessed, and `target_entities`/
`signals`/`freshness` are deliberately out of Fit's scope (freshness is
Verification's job, signals are Intent's). All three new scores are
computed once, at pipeline-completion time, and don't update themselves
as new evidence or signals would appear on a re-crawl — same disclosed
non-live-updating limitation every score in this codebase carries since
Session 7.

**NEXT** — per `AUDIT_BPO_CRM.md`'s approved phase table: Phase 9 (CRM
Integration — moved up from its original position specifically because a
tenant gets value from Phases 2–8 landing in their CRM well before a
knowledge graph exists) is the next unstarted phase in sequence, and now
has a real Opportunity Score to export/push — or the still-open
remainders of Phase 2 (multi-provider source discovery) and Phase 3
(adaptive Playwright-based fetcher), pending direction from whoever's
driving next.

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
