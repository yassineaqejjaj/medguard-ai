# API reference

Interactive documentation is served by the running API at **`/api/docs`** (Swagger UI) and **`/api/openapi.json`**; a snapshot of the
spec is committed as [openapi.json](openapi.json) (47 operations). Base path `/api/v1`.

**Authentication.** `Authorization: Bearer <OIDC access token>` from Keycloak (audience `medguard-api`, claims `org` and
`realm_access.roles`). The only other credential accepted is a CI token (`mgt_...`), and only on `GET /ci/gate`.
**Errors** are JSON with an HTTP status: 401 (no or invalid token), 403 (role), 404 (not found *or another tenant's*), 409 (state
conflict), 422 (validation), 429 (rate limit, with `Retry-After`).

Roles: `viewer` < `reviewer` < `engineer` < `admin` for ordinary actions. Exact-role actions are marked **(exact)**.

| Area | Endpoint | Who | Purpose |
|---|---|---|---|
| Identity | `GET /me` | any | Resolved user, organisation, role |
| Dashboard | `GET /dashboard/summary` | any | Counts, pass rate, failures by severity, trend, recent runs (all computed from data) |
| Applications | `GET /systems`, `POST /systems` | any / engineer+ | List; create an application with its first version and endpoint |
| | `POST /systems/{id}/versions`, `GET /versions` | engineer+ / any | Add a version (own endpoint and secret); list versions |
| Scenarios | `GET/POST /suites`, `GET /suites/{id}` | any / engineer+ | Suites and their current scenarios |
| | `POST /suites/{id}/cases`, `PUT /cases/{id}`, `POST /cases/{id}/duplicate` | engineer+ | Create; edit (writes a new immutable version); duplicate |
| | `POST /cases/{id}/validation` | reviewer, admin **(exact)** | Human validation status with justification |
| | `PUT /suites/{id}/order`, `POST /suites/{id}/import`, `GET /suites/{id}/export?format=json\|csv` | engineer+ / any | Reorder; all-or-nothing import; export |
| Runs | `POST /runs`, `GET /runs`, `GET /runs/{id}`, `GET /runs/{id}/items` | engineer+ / any | Launch a campaign (queued to the worker); status; per-scenario results with criteria and evidence |
| Review | `GET /reviews/queue?status=&run_id=`, `GET /run-items/{id}/review` | any | Flagged results, critical first; one case with its history |
| | `POST /run-items/{id}/reviews` | reviewer, admin **(exact)** | Record a decision (append-only) |
| | `POST /run-items/{id}/arbitrate` | admin **(exact)** | Close a disputed case |
| | `GET /judge/agreement` | reviewer, admin **(exact)** | Judge vs human agreement (kappa, false passes) |
| Comparison | `GET /compare?baseline_run=&candidate_run=` | any | Regressions, fixes, category deltas (same application and suite) |
| Release gate | `GET/PUT /systems/{id}/gate-policy` | any / admin **(exact)** | Blocking rules per application |
| | `POST /runs/{id}/gate`, `GET /runs/{id}/gate`, `GET /gates`, `GET /gates/{id}` | engineer+ / any | Evaluate (PASS, FAIL, REVIEW_REQUIRED, policy snapshotted); read |
| | `POST /gates/{id}/decision` | admin **(exact)** | Sign off release or block; release refused unless the gate is PASS |
| CI/CD | `GET /ci/gate?system=&version=` | CI token | Latest gate status with `exit_code` (0 PASS, 1 FAIL, 2 REVIEW_REQUIRED, 3 not evaluated) |
| | `GET/POST /tokens`, `DELETE /tokens/{id}` | admin **(exact)** | Manage CI tokens (secret shown once) |
| Evidence | `POST /runs/{id}/reports?format=html\|json\|pdf`, `GET /reports`, `GET /reports/{id}/download` | engineer+ / any | Generate, list, download reports with integrity hash |
| | `GET /evidence`, `GET /evidence/{id}/download` | reviewer+ | Stored responses; each download re-verifies its SHA-256 |
| | `GET /audit?limit=&before_id=&action=` | admin | Audit entries plus hash-chain verification |
| Settings | `GET /settings`, `PUT /settings/retention`, `POST /settings/retention/purge` | any / admin **(exact)** | Retention period; purge expired responses and reports |
| Ops | `GET /healthz`; `GET /metrics` (internal only) | none | Liveness; Prometheus metrics |

## Scenario pass conditions

`pass_conditions` is a strict object (unknown keys are rejected):

```json
{
  "require_json": true,
  "required_fields": ["answer", "citations"],
  "require_citations": true,
  "reference_sections": ["§1.1", "§2.1"],
  "must_contain": ["4 weeks"],
  "must_not_contain": [" mg"],
  "max_chars": 1200,
  "max_latency_ms": 2000,
  "forbidden_sensitive": ["PAT-000123"]
}
```

Judge criteria (`criteria`): `faithfulness`, `relevance`, `citation_accuracy`, `unjustified_claims`, `uncertainty`, `boundaries`,
`sensitive_requests`, `consistency` (the last is not yet a multi-prompt check).

## Application contract (what the HTTP adapter expects)

`POST <endpoint>` with `{"question": "<scenario input>"}` and JSON back with `answer` (string) and `citations` (list of
`{doc, section, quote}`). The request template and response mapping are fields on the application version (default shown); the
demonstration assistant in `apps/demo-assistant` is a working example.

## CI example

```bash
MEDGUARD_TOKEN=mgt_... scripts/medguard-gate.sh --url https://medguard.example --system "My assistant" --version v1.2.0
# prints the status and reasons; exits 0 / 1 / 2 / 3 / 4 (4 = could not reach MedGuard)
```
