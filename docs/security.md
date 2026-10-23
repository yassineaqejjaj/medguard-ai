# Security model

Not a certification. These are the controls that exist in the code, what each one is tested by, and what is not covered.

## Controls

| Area | Control | Where / test |
|---|---|---|
| Authentication | OIDC (Keycloak). The API verifies signature, issuer, audience and expiry on every request. Web uses authorization code + PKCE (S256); tokens stay in `sessionStorage`. | `security.py`; `test_auth_rbac_audit.py` (missing, garbage, expired, wrong audience, wrong key) |
| Authorisation | Four roles from the IdP. Hierarchy for ordinary actions; **exact-role** checks for duties that must not be inherited (validate scenarios, review, arbitrate, sign off releases, retention, tokens). | `require`, `require_roles`; role tests in every module |
| Tenant isolation | Organisation comes from the token, never from client input. PostgreSQL row-level security (`FORCE`) on every tenant table, bound per transaction; the app role is not a superuser and cannot bypass RLS. API queries are also scoped. | `0002_rls_and_grants.py`; `test_tenant_isolation.py` plus cross-tenant 404 tests on systems, suites, runs, reviews, gates, reports, tokens |
| Secrets at rest | Endpoint credentials encrypted with AES-256-GCM (random nonce); never returned by the API and never written to the audit log. | `crypto.py`; `test_systems_dashboard.py` |
| SSRF | The worker calls user-supplied URLs. Scheme allowlist, DNS resolved once, **every** address must be public (loopback/private allowed only by explicit setting; link-local, metadata, multicast, reserved always blocked), connection pinned to the vetted IP (no DNS rebinding), redirects not followed, response capped at 1 MB. | `evaluation/ssrf.py`, `adapters.py`; `test_engine_units.py` (this test caught a multicast bypass during development) |
| Input validation | Pydantic models with length caps and strict enums; `extra=forbid` on pass conditions so a typo cannot silently disable a check; import is all-or-nothing with per-row errors. SQL only through bound parameters. | `schemas.py`, `suites.py`; `test_suites_api.py` |
| Untrusted output | Application responses are untrusted. Report HTML is auto-escaped and served as an attachment under a `sandbox` CSP. CSV export neutralises spreadsheet formulas. The judge prompt fences the answer and strips closing tags. | `reports.py`, `suites.py`, `judge.py`; XSS, CSV and fence tests |
| Judge safety | A judge verdict never overrides a deterministic failure; critical/high results that depend on the judge alone, low confidence, errors and disagreements go to a human. | `scoring.py`; `test_engine_units.py`, `test_gate_compare.py` |
| Integrity | Audit log is hash-chained and insert-only for the app role (also reviews, release decisions, gate evaluations); chain verified on read. Evidence objects carry SHA-256 re-checked on download. Reports carry a manifest hash. | `audit.py`, `storage.py`; tamper tests |
| Rate limiting | 300 requests/minute per user or CI token, Valkey-backed; fails open if Valkey is down (availability over strictness for this one control). | `ratelimit.py`; `test_ratelimit_metrics.py` |
| CI tokens | `mgt_` tokens, scope `gate:read`, stored as SHA-256 only, shown once, revocable; they open one endpoint and nothing else. | `gates.py`; `test_gate_compare.py` |
| Hardening | Containers run as non-root; `/metrics` is not routed through the reverse proxy; `X-Content-Type-Options: nosniff` and `Cache-Control: no-store` on API responses; errors never leak internals. | `Dockerfile`s, `Caddyfile`, `main.py` |

## Dependency checks

`pip-audit` (Python) and `pnpm audit --prod` (JavaScript) reported no known vulnerabilities when this was last run (2026-10-22).
`scripts/check_licenses.py` enforces the licence policy. Re-run all three before each release.

## Not covered / known gaps

- No malware scanning of imported files; no antivirus on evidence.
- The demo realm contains demo users with known passwords. Remove them outside local use.
- Keycloak runs in `start-dev` mode in `compose.yaml`; use a production configuration for real deployments.
- Rate limiting is per principal, not per IP; unauthenticated traffic is only limited by what the reverse proxy does.
- The audit chain proves tampering after the fact; it does not prevent a database owner from rewriting history and recomputing hashes. Ship the chain head hash (shown in every report) to an external system for stronger guarantees.
- No penetration test has been performed.
