# Security

This document covers what is implemented today (Phase 1–3). It will grow as
later phases add the rest of master-spec §50–§52 (rate limiting, sandboxed
browser workers, resource quotas, legal/compliance engine, prompt-injection
defense at the agent boundary once Phase 8 adds agents).

## SSRF protection (crawler)

`app/engines/crawler/ssrf_guard.py` is invoked before every HTTP request the
crawler makes, and again on every redirect hop:

1. Scheme must be `http` or `https`.
2. Hostname is resolved via DNS; every resolved IP is checked against:
   loopback, link-local, private (RFC1918), unique-local, multicast,
   reserved, and unspecified ranges (using `ipaddress.ip_address(...).is_*`).
   Any match rejects the request.
3. Cloud metadata endpoints (`169.254.169.254`, `metadata.google.internal`,
   fd00:ec2::254, etc.) are explicitly blocked via the link-local/reserved
   check above plus an explicit denylist as defense in depth.
4. The check re-runs per redirect (not just the initial URL), so a
   first-party domain that redirects to an internal address is rejected.
5. Response bodies are streamed with a hard cap (`MAX_RESPONSE_BYTES`,
   default 10 MB) to bound memory/storage use per page.

**Known residual gap:** the guard resolves and validates the hostname, but
does not pin the actual TCP connection to that validated IP — httpx performs
its own resolution when it connects. A narrow-window DNS-rebinding attack
(the name resolves safely at validation time, then differently a moment
later when httpx connects) is therefore not fully closed today. Fully
closing it needs a custom transport that connects directly to the
pre-validated address; tracked as a Phase 4/11 hardening item rather than
claimed as done.

This is enforced in code, not just documented: see
`backend/tests/test_ssrf_guard.py`.

## Tenant isolation

Two independent layers, not one:

1. **App layer.** Every table below the organization level carries (directly
   or via FK chain) `organization_id`. Every repository method that reads or
   writes research data takes the caller's `organization_id` (resolved
   server-side from the JWT, never from a client-supplied parameter) and
   filters on it. There is no code path in `app/repositories/` that queries
   across organizations. RBAC role checks (`app/core/deps.py::require_role`)
   gate write operations beyond the caller's role.
2. **Database layer — PostgreSQL Row-Level Security.** `research_events`,
   `sources`, `crawl_pages`, `research_results`, and `tenant_quotas` all have
   RLS policies comparing their (denormalized, indexed) `organization_id`
   column against `current_setting('app.current_tenant', true)`, enabled
   with `FORCE ROW LEVEL SECURITY` so it applies even to the table-owning
   role. `app/core/database.py` sets that session variable via a SQLAlchemy
   `after_begin` listener, re-applied on every transaction (not just the
   first — each repository call commits its own transaction, and `SET
   LOCAL` only lives for the transaction it was issued in).

   **This layer is only load-bearing when the app connects as a
   non-superuser role — that is not yet true of every environment this repo
   ships.** Postgres superusers unconditionally bypass RLS regardless of
   `FORCE`; this is a hard Postgres rule, not a configuration option. The
   single `bpo` role used throughout `docker-compose.yml` and
   `.env.example` for migrations *and* runtime traffic is created by the
   official `postgres` Docker image as a **superuser** (that's what
   `POSTGRES_USER` does), so as shipped in Docker Compose / a naive
   production deployment following the same pattern, this second layer is
   currently a no-op — the app-layer scoping in point 1 is the only real
   protection today. This was caught (not assumed) via real-CI testing: a
   prior version of this document asserted the connecting role was
   "confirmed non-superuser," which was false — `tests/test_rls.py` passed
   locally against a differently-configured local Postgres but failed the
   first time it actually ran against GitHub Actions' `postgres:16-alpine`
   service container, exactly because that assumption didn't hold there.
   CI now creates a second, ordinary (non-superuser, no `BYPASSRLS`) role,
   `bpo_app`, after migrations run, and points `tests/test_rls.py` at it —
   so the RLS policies themselves are proven correct against a real,
   properly-scoped role. **Extending that same role separation to
   `docker-compose.yml` (and any real deployment) — a distinct
   least-privileged runtime role for the API/worker, separate from the
   schema-owning migration role — is still open, tracked below.**

   This means a bug in the app-layer filtering — a missing `WHERE
   organization_id = ...`, a copy-pasted query — would still be blocked by
   the database itself, and does not merely rely on someone reviewing that
   the app layer got it right in every function forever.

   `research_jobs` itself is deliberately **not** RLS-protected. Enforcing
   it would create a bootstrapping deadlock: the worker's first read of a
   job (`get_research_job_for_worker`) happens before it knows the job's
   `organization_id` — it has to read the row to find that out, but RLS
   would need the tenant context set before that read to allow it. Tenant
   isolation on `research_jobs` stays app-layer only (tested —
   `tests/test_research.py::test_organizations_cannot_see_each_others_research`).
   The same class of ordering problem shows up wherever a new organization
   or job is minted mid-request — see `app/repositories/auth_repository.py`
   for how signup handles it (generate the UUID before any insert, set
   tenant context immediately, then force a fresh transaction so the
   listener actually re-fires with it).

   Verified against a real PostgreSQL, not asserted: `tests/test_rls.py`
   inserts without a tenant context (rejected), with the correct context
   (succeeds), under the wrong tenant's context (rejected), and confirms a
   `SELECT` never returns another tenant's rows — self-skips without a
   reachable Postgres, and runs for real in CI (`.github/workflows/ci.yml`'s
   `backend` job now starts a `postgres:16-alpine` service and applies
   migrations before the test step for exactly this).

   One implementation subtlety worth recording because it silently produces
   the *wrong* failure mode if missed: `current_setting('app.current_tenant',
   true)` only returns `NULL` the first time a session touches that
   (undeclared, session-scoped) custom setting. Once any transaction on a
   pooled connection has done `SET LOCAL app.current_tenant = ...`, a later
   transaction on the *same* connection that forgets to set it again gets
   `''` back, not `NULL` — and `''::uuid` raises a hard error instead of the
   policy evaluating to false. The policies use
   `NULLIF(current_setting(...), '')::uuid` specifically to keep "no tenant
   context set" failing closed (no rows, always) rather than sometimes
   erroring depending on what a pooled connection was previously used for.

## Secrets

- All credentials/keys live in environment variables, loaded via
  `pydantic-settings`. `.env` is git-ignored; `.env.example` lists every key
  with a placeholder, never a real value.
- JWT signing secret (`SECRET_KEY`) must be overridden in any non-local
  environment; the app refuses to start with the example default when
  `ENVIRONMENT=production`.
- Passwords are hashed with bcrypt (passlib `CryptContext`), never logged,
  never returned in any API response.

## Untrusted web content

Crawled/extracted text is stored and displayed as data. Nothing in the
Phase 1–3 pipeline passes extracted page content into a component that
interprets it as instructions (there is no LLM/agent loop yet). This
boundary is being called out now, ahead of Phase 8, because it is the kind
of thing that is easy to violate by accident once an "AI Gateway" exists:
when Phase 8 lands, extracted content must be passed to models as clearly
delimited *data* in the prompt, never concatenated into the system/instruction
channel, and any model output derived from page content must be treated as
a claim to verify, not a command to execute.

## Known dependency advisories (frontend, accepted for now)

`npm audit` flags two moderate advisories as of this writing; both were
evaluated rather than silently ignored:

- **esbuild ≤0.24.2 / vite ≤6.4.2** (GHSA-67mh-4wv8-2f99): the Vite *dev*
  server will respond to requests from any origin. This only matters if the
  dev server (`npm run dev`) is exposed beyond localhost, which it isn't in
  this repo's Docker Compose setup or CI. The fix requires Vite 8, a major
  bump with a wider blast radius than justified for a dev-only exposure —
  revisit when upgrading the frontend toolchain generally, not as a reactive
  patch.
- **react-router / react-router-dom 6.0.0–7.17.0** (open redirect via
  backslash in `<Link>`/`useNavigate`, CVE-2025-68470-adjacent): fixed only
  in 7.18.0+, i.e. there is no patched 6.x release to pin to. This app never
  passes user-controlled or externally-sourced strings into a `<Link to>` or
  `navigate()` call — every route target is either a static path or built
  from a UUID our own backend generated (e.g. `/research/${job.id}`) — so
  the exploitable surface for this specific advisory doesn't exist in this
  codebase today. Tracked for the eventual react-router v7 migration rather
  than accepted permanently.

## What's not yet implemented (tracked for later phases)

- **A least-privileged, non-superuser runtime role for `docker-compose.yml`
  and production deployments**, distinct from the schema-owning migration
  role — see "Tenant isolation" above. Without it, PostgreSQL RLS is a
  no-op in any environment following this repo's current Compose pattern;
  CI now proves the RLS policies themselves are correct against such a
  role (`bpo_app`), but nothing outside CI uses one yet.
- Rate limiting on the public API (Phase 11 / hardening pass)
- API key auth for programmatic/MCP clients (Phase 9/11)
- Browser sandbox isolation for the Playwright worker pool (Phase 4)
- Full immutable audit log across all mutating actions (Phase 11)
- Dependency/secret scanning gate in CI (Phase 11)
- robots.txt / rate-limit / domain-policy compliance engine (Phase 4/10)
