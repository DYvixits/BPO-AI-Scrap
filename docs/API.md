# API (Phase 1–3)

Full interactive docs (auto-generated OpenAPI): run the app and visit `/docs`
or fetch `/openapi.json`. This file is the human-readable summary.

All endpoints are prefixed `/api/v1`. All request/response bodies are JSON.

## Auth

### `POST /auth/register`

Creates a new user **and** a new organization (the user becomes its admin —
joining an existing org by invite is a Phase 11 feature).

```json
// request
{ "email": "you@company.com", "password": "at least 8 chars", "full_name": "Ada Researcher", "organization_name": "Acme Research Co" }
// response 201
{ "access_token": "...", "refresh_token": "...", "token_type": "bearer" }
```

### `POST /auth/login`

```json
{ "email": "you@company.com", "password": "..." }
// -> TokenPair, same shape as register
```

### `POST /auth/refresh`

```json
{ "refresh_token": "..." }
// -> new TokenPair
```

### `GET /auth/me` (auth required)

```json
{
  "id": "uuid", "email": "you@company.com", "full_name": "Ada Researcher",
  "organization": { "id": "uuid", "name": "Acme Research Co", "slug": "acme-research-co" },
  "role": "admin"
}
```

## Research

All routes below require `Authorization: Bearer <access_token>` and are
scoped to the caller's organization — no route accepts an `organization_id`
parameter from the client.

### `POST /research`

```json
// request
{ "query": "African fintech companies founded after 2020 with funding above $1M", "mode": "balanced", "config": {} }
// response 201
{
  "id": "uuid", "query": "...", "status": "queued", "mode": "balanced",
  "config": { "max_results": 6 },
  "objective": {
    "target_entities": ["company"],
    "geography": ["Africa"],
    "industry": ["fintech"],
    "company_size_min": null, "company_size_max": null,
    "required_attributes": [],
    "signals": ["funding"],
    "freshness": "any",
    "matched_keywords": { "geography": ["african"], "industry": ["fintech"], "signals": ["funding"] }
  },
  "error": null,
  "created_at": "...", "started_at": null, "completed_at": null
}
// or 429 if the organization's TenantQuota.max_concurrent_research_jobs
// (standard tier default: 2) is already reached by other non-terminal jobs
{ "detail": "Concurrent research job limit reached (2/2) — wait for a running research job to finish, or upgrade your plan." }
```

`mode` is one of `quick | balanced | deep | verified | investigation |
custom`; each has default parameters (`ARCHITECTURE.md` §"provider
abstractions" / `research_orchestrator.py::MODE_DEFAULTS`). `config`
overrides individual fields on top of the mode's defaults.

`objective` is computed once at creation by the heuristic Query
Intelligence Engine (`app/engines/query_intelligence`) — no LLM call, pure
keyword matching — and never changes afterward. `matched_keywords` records
the literal words in the query that produced each field, so every tag is
explainable rather than a black box. The Search Strategy Engine
(`app/engines/search_strategy`) then turns this objective into up to 4
targeted search queries for the worker, deduplicated by URL before
crawling. See `ARCHITECTURE.md` §1 and §7 for the full flow.

### `GET /research`

Returns the caller's organization's jobs, newest first — a `ResearchJob[]`
(same shape as the create response, no `events`).

### `GET /research/{id}`

Same shape plus `events: ResearchEvent[]` (the append-only progress log).
404 if the job doesn't exist **or** belongs to a different organization —
the two cases are indistinguishable by design (no cross-tenant existence
leak).

### `GET /research/{id}/companies` (Phase 5 + Phase 6 + Phase 7)

```json
[
  {
    "id": "uuid",
    "canonical_name": "Kesho Finance",
    "primary_domain": "kesho.example.com",
    "description": "Mobile lending platform for small businesses in East Africa.",
    "match_confidence": 0.7,
    "aliases": [
      { "alias_type": "domain", "value": "kesho.example.com", "source_url": "https://kesho.example.com" },
      { "alias_type": "domain", "value": "crunchbase.example.com", "source_url": "https://crunchbase.example.com/kesho" },
      { "alias_type": "name", "value": "Kesho Finance", "source_url": "https://kesho.example.com" }
    ],
    "confidence_score": {
      "status": "corroborated",
      "source_count": 2,
      "source_diversity": 2,
      "freshness_score": 1.0,
      "evidence_completeness": 1.0,
      "overall_score": 0.89
    },
    "evidence": [
      { "source_url": "https://kesho.example.com", "domain": "kesho.example.com", "excerpt": "Kesho Finance closed a $4M seed round..." },
      { "source_url": "https://crunchbase.example.com/kesho", "domain": "crunchbase.example.com", "excerpt": "Crunchbase profile: Kesho Finance, fintech, Nairobi, Kenya." }
    ],
    "signals": [
      {
        "signal_type": "funding",
        "polarity": "positive",
        "matched_keyword": "raised",
        "excerpt": "Kesho Finance closed a $4M seed round led by regional investors.",
        "source_url": "https://kesho.example.com",
        "base_weight": 1.0,
        "decayed_strength": 0.94
      }
    ]
  }
]
```

Companies produced by the Entity Resolution Engine (`app/engines/
entity_resolution`) once crawling ends — groups pages that refer to the
same real-world company (e.g. a company's own site plus its Crunchbase
profile) instead of surfacing every crawled page as an unrelated flat
result. `match_confidence` is `1.0` for a company built from a single
domain (nothing to disambiguate) and `0.7` when pages from different
domains were merged on a name match alone — a disclosed heuristic number,
not a verified claim (see `SECURITY.md`). Always empty until `status ==
"completed"`; 404 under the same rules as `GET /research/{id}`.
`research_results[].company_id` (nullable) links each result to one of
these companies.

`confidence_score` (Phase 6, `app/engines/verification`) is `null` until
the Verification Engine has run (same lifecycle as `aliases`). `status` is
one of `unverifiable | uncertain | corroborated | verified | outdated` —
5 of the master spec's 7 Truth Engine states; `probable`/`contradicted`
are not computed, since both need claim-level agreement/conflict
detection this codebase's claim extraction doesn't provide (see
`ARCHITECTURE.md` §7). A company is `verified` only with evidence from at
least 3 distinct domains. `evidence` lists every crawled page counted
toward that score — the auditable trail behind the number, not a
claim-by-claim fact check.

`signals` (Phase 7, `app/engines/commercial_signals`) lists commercial
events (funding, hiring, a leadership change, ...) found by keyword match
on the company's own crawled pages — the same disclosed vocabulary Query
Intelligence uses to parse `objective.signals` from the user's query, now
applied to what the pages actually say. `signal_type` is one of `hiring |
expansion | funding | acquisition | leadership_change | product_launch |
digital_transformation | layoffs | closure`; `polarity` is `positive` or
`negative`. `decayed_strength` fades `base_weight` (currently a uniform
`1.0` for every type) toward `0` the longer ago the source page was
crawled — see `ARCHITECTURE.md` §7 for the decay curve and its
proxy-for-recency limitation (no real event date is extracted from the
page text). Empty until the pipeline has run; a company can have zero
signals even after completion if nothing on its pages matched.

### `GET /research/{id}/results`

```json
[
  { "id": "uuid", "title": "Company X", "url": "https://...", "snippet": "...", "confidence": 0.8, "company_id": "uuid or null" }
]
```

`confidence` here is the Phase 1–3 basic relevance score (see
`ARCHITECTURE.md` and `SECURITY.md`/`PHASE_PLAN.md` for why this is
explicitly not a "verified" score) — always empty until `status ==
"completed"`.

### `WS /research/{id}/ws`

Browser WebSocket clients can't set headers, so auth is a query param:
`wss://.../research/{id}/ws?token=<access_token>`. Streams the same event
kinds as the `events` array on the job (`status.changed, search.completed,
sources.discovered, page.completed, page.failed, crawl.expanded,
crawl.stopped_early, entities.resolved, verification.completed,
signals.detected, research.completed, research.failed`), as JSON text
frames, as they happen.

`page.completed`'s payload also carries `duplicate_reason` (Phase 4):
`"exact_hash"` when the page's content is byte-identical to one already
crawled in this job, `"near_duplicate"` when it's a high-similarity match
(e.g. the same page with a timestamp or session token embedded), or `null`
when it's not a duplicate — `duplicate` is `true` for either reason.
A duplicate page is still crawled and recorded (its `crawl_pages` row and
`structured_data` exist), it just doesn't produce a second
`research_results` row.

`crawl.expanded` (`{"from": "<url>", "new_candidates": N}`) fires when a
crawled page yields new same-domain links worth considering — the crawl
frontier growing, not a completed page. `crawl.stopped_early`
(`{"reason": "objective_satisfied" | "diminishing_returns", "pages_crawled":
N}`) fires at most once per job, only when the crawl stopped before
exhausting its `max_pages` budget — either because every `required_attribute`
the query asked for was found, or because a run of pages in a row found
nothing new. See `ARCHITECTURE.md` §7 for the scoring/tracking behind both.

`entities.resolved` (`{"count": N}`, Phase 5) fires once per job, after
the crawl loop ends, once the Entity Resolution Engine has grouped crawled
pages into `N` companies — never fires at all if no page yielded a usable
company name (`N` would be 0, so there's nothing to report). See
`GET /research/{id}/companies` above.

`verification.completed` (`{"counts": {"verified": 1, "corroborated": 2,
...}}`, Phase 6) fires immediately after `entities.resolved`, under the
same "only if there's at least one company" condition — one count per
Truth Engine status produced for this job's companies (statuses with a
zero count are omitted, not sent as `0`). See `GET /research/{id}/companies`
above for what each status means.

`signals.detected` (`{"counts": {"funding": 1, "hiring": 2, ...}}`,
Phase 7) fires immediately after `verification.completed`, but only if at
least one signal was found anywhere in the job — unlike
`entities.resolved`/`verification.completed`, it's entirely possible for
a job to complete with real companies and zero signals (most crawled
pages don't happen to mention funding, hiring, etc.), and this event
simply doesn't fire in that case. See `GET /research/{id}/companies`
above for what each signal type means.

## Health

### `GET /health`

```json
{ "status": "ok", "checks": { "database": true, "redis": true } }
```

`status` is `"degraded"` (not an error) if either check fails — used for
liveness/readiness probes, not user-facing.
