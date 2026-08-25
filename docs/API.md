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
  "config": { "max_results": 6 }, "error": null,
  "created_at": "...", "started_at": null, "completed_at": null
}
```

`mode` is one of `quick | balanced | deep | verified | investigation |
custom`; each has default parameters (`ARCHITECTURE.md` §"provider
abstractions" / `research_orchestrator.py::MODE_DEFAULTS`). `config`
overrides individual fields on top of the mode's defaults.

### `GET /research`

Returns the caller's organization's jobs, newest first — a `ResearchJob[]`
(same shape as the create response, no `events`).

### `GET /research/{id}`

Same shape plus `events: ResearchEvent[]` (the append-only progress log).
404 if the job doesn't exist **or** belongs to a different organization —
the two cases are indistinguishable by design (no cross-tenant existence
leak).

### `GET /research/{id}/results`

```json
[
  { "id": "uuid", "title": "Company X", "url": "https://...", "snippet": "...", "confidence": 0.8 }
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
sources.discovered, page.completed, page.failed, research.completed,
research.failed`), as JSON text frames, as they happen.

## Health

### `GET /health`

```json
{ "status": "ok", "checks": { "database": true, "redis": true } }
```

`status` is `"degraded"` (not an error) if either check fails — used for
liveness/readiness probes, not user-facing.
