# MedGuard AI — Technical Architecture (Phase 1)

> Trust every AI decision. Prove every result.
> MedGuard does not issue medical or regulatory certification. Nothing here is claimed to be automatically GDPR / HDS / AI Act compliant.

## 1. Principles

- Modular monolith: one Next.js frontend, one FastAPI API, Celery workers (same Python package as the API), PostgreSQL, Valkey, SeaweedFS, Keycloak, Caddy, local LLM server.
- 100 % OSI-licensed stack, fully self-hostable, runs air-gapped once images and model weights are pulled.
- Synthetic data only. No real patient data by default.
- A single LLM-judge score is never evidence of clinical safety: every verdict is combined with deterministic checks and a mandatory human-review policy for critical cases.

## 2. Component diagram

```text
                    ┌───────────────────────────── Caddy (TLS, reverse proxy) ───────────────────────────┐
                    │                                                                                    │
 Browser ──► web (Next.js) ──REST/JSON──► api (FastAPI) ──► PostgreSQL (RLS, tenant isolation)           │
     │                                       │  │  └──────► SeaweedFS (S3 API): evidence, reports         │
     │  OIDC (PKCE)                          │  └─ enqueue ► Valkey ◄── Celery workers                    │
     └──────────► Keycloak ◄── JWKS ─────────┘                         │   │                              │
                                                                       │   ├─► Target AI app (HTTP adapter, SSRF-guarded)
                                                                       │   └─► Judge LLM: vLLM (GPU) | llama.cpp (CPU)  — Qwen3-8B
 OpenTelemetry SDK (api, workers) ─► OTel Collector ─► Prometheus
```

Deployment units (compose): `caddy`, `web`, `api`, `worker`, `postgres`, `valkey`, `seaweedfs`, `keycloak`, `llm` (profile `gpu` = vLLM, profile `cpu` = llama.cpp), `otel-collector`, `prometheus`.

## 3. Evaluation flow

1. Engineer creates an **Evaluation Run** (`system_version` × `test_suite`) → API validates, stores `run` (status `queued`), one `run_item` per test case, enqueues a Celery job.
2. Worker, per item: call target through the **HTTP adapter** (timeout, size cap, SSRF guard) → store raw response as evidence object (SHA-256 recorded).
3. **Deterministic checks** (`evaluation/deterministic`) run first: JSON validity, required fields, citations, exact rules, length limits, latency, API errors, forbidden fictitious sensitive strings.
4. **LLM judges** (`evaluation/llm_judges`) run via the local OpenAI-compatible endpoint (vLLM / llama.cpp server — protocol only, no proprietary service): temperature 0, fixed seed, fixed max tokens, JSON schema–constrained output, versioned prompts. Output is validated against the Pydantic `CriterionResult`; invalid JSON → one retry → `error` status + human review.
5. **Scoring** (`evaluation/scoring`) aggregates per criterion/category and applies the **review policy**: `severity=critical` fail, judge low confidence, judge/deterministic disagreement or judge error ⇒ `needs_human_review`.
6. **Human review** resolves flagged items (≥1 reviewer; critical failures require explicit decision; two reviewers disagreeing ⇒ `disputed`, admin arbitration).
7. **Release Gate** evaluates blocking rules against a run (optionally vs. a baseline run) → `PASS | FAIL | REVIEW_REQUIRED`. Critical failures are evaluated independently of averages. CI reads it via `GET /api/v1/gates/{run_id}/status` (machine token) with exit-code-friendly JSON. Final release decision is a recorded human action.
8. **Evidence Center** builds HTML/JSON/PDF reports (Jinja2 + WeasyPrint), stores them in SeaweedFS with a manifest hash; every report embeds run id, scenario versions, model versions, prompt versions, parameters, audit hash.

## 4. Data model (PostgreSQL)

All tenant tables carry `org_id` (NOT NULL, FK) and have Row-Level Security: `USING (org_id = current_setting('app.org_id')::uuid)`. The API sets `app.org_id` per transaction (`SET LOCAL`); the application DB role is not a superuser and not `BYPASSRLS`. API-layer filtering is a second, independent layer.

```text
organizations(id, name, slug, retention_days, created_at)
users(id, org_id, oidc_sub, email, display_name, role[admin|engineer|reviewer|viewer], active)
ai_systems(id, org_id, name, description, purpose, usage_context, owner, model_name, doc_sources jsonb,
           created_at, updated_at)
ai_system_versions(id, org_id, system_id, version_label, endpoint_url, auth_type, auth_secret_enc,
                   request_template jsonb, response_mapping jsonb, timeout_s, created_at)
test_suites(id, org_id, name, description, created_at)
test_cases(id, org_id, suite_id, case_key, version, category, input, reference_context, expected_behavior,
           criteria jsonb, severity[low|medium|high|critical], pass_conditions jsonb,
           validation_status[draft|validated|rejected], position, created_at)  -- immutable per version
evaluation_runs(id, org_id, system_version_id, suite_id, status, params jsonb, judge_model, judge_model_digest,
                judge_prompt_versions jsonb, started_by, started_at, finished_at)
run_items(id, org_id, run_id, test_case_id, test_case_version, response_evidence_id, latency_ms,
          status[pending|passed|failed|error|needs_review], needs_review bool, review_reasons jsonb)
criterion_results(id, org_id, run_item_id, kind[deterministic|llm_judge], criterion, score, status,
                  justification, evidence jsonb, confidence, requires_review, judge_prompt_version)
reviews(id, org_id, run_item_id, reviewer_id, decision[accept|reject], error_severity, annotations jsonb,
        justification, created_at)  -- append-only
review_resolutions(id, org_id, run_item_id, status[agreed|disputed|arbitrated], final_decision, resolved_by, ts)
gate_policies(id, org_id, system_id, name, rules jsonb)   -- e.g. max_critical_failures=0, min_category_score
gate_evaluations(id, org_id, run_id, baseline_run_id, policy_id, status, details jsonb, evaluated_at)
release_decisions(id, org_id, gate_evaluation_id, decided_by, decision, justification, ts)
evidence_objects(id, org_id, run_id, kind, s3_key, sha256, size, created_at)
reports(id, org_id, run_id, format, evidence_object_id, manifest_sha256, created_at)
audit_log(id, org_id, actor_id, action, entity_type, entity_id, before jsonb, after jsonb,
          prev_hash, hash, ts)    -- hash-chained, INSERT-only (no UPDATE/DELETE grants)
api_tokens(id, org_id, name, token_hash, scopes, created_by, last_used_at)  -- CI tokens
```

## 5. API contract (summary, `/api/v1`, OpenAPI at `/docs`)

| Area | Endpoints |
|---|---|
| Auth | `GET /me` (OIDC bearer JWT validated against Keycloak JWKS) |
| Systems | `GET/POST /systems`, `GET/PATCH /systems/{id}`, `POST /systems/{id}/versions`, `POST /systems/{id}/versions/{vid}/ping` |
| Suites | `GET/POST /suites`, `POST /suites/{id}/import` (JSON/CSV), `GET /suites/{id}/export?format=`, `POST/PUT/DELETE /suites/{id}/cases`, `POST /cases/{id}/duplicate` |
| Runs | `POST /runs`, `GET /runs`, `GET /runs/{id}`, `GET /runs/{id}/items`, `POST /runs/{id}/cancel` |
| Review | `GET /reviews/queue`, `POST /run-items/{id}/reviews`, `POST /run-items/{id}/arbitrate` |
| Compare | `GET /compare?base={run}&candidate={run}` |
| Gate | `PUT /systems/{id}/gate-policy`, `POST /runs/{id}/gate`, `GET /gates/{run_id}/status`, `POST /gates/{id}/decision` |
| Evidence | `GET /evidence`, `POST /runs/{id}/reports?format=html|json|pdf`, `GET /reports/{id}/download`, `GET /audit` |
| Dashboard | `GET /dashboard/summary` |
| Ops | `GET /healthz`, `GET /metrics` |

Errors: RFC 7807 problem+json. Rate limiting per user/token (Valkey-backed sliding window). All inputs are Pydantic models with strict types and length caps; SQL only via SQLAlchemy bound parameters.

## 6. Security design

- **AuthN/Z**: Keycloak OIDC; API verifies JWT (issuer, audience, signature, exp). Role from realm role claim, mapped to Admin/Engineer/Reviewer/Viewer; enforced by dependency per route.
- **Tenancy**: org derived from token claim `org` → `organizations`; never from client input. RLS + API filters + cross-tenant tests.
- **Secrets**: target-app credentials encrypted at rest with AES-256-GCM (`cryptography`, BSD/Apache) using a key from env/secret file; never returned by the API.
- **SSRF guard**: scheme allowlist, DNS resolution then IP check against private/loopback/link-local/metadata ranges (blocked unless org admin allowlists a host or `MEDGUARD_ALLOW_PRIVATE_TARGETS=true` for demo), no redirects followed to blocked ranges, response size cap.
- **Audit**: hash-chained append-only log; verification endpoint.
- **Retention**: per-org `retention_days`; scheduled Celery purge of evidence and responses (audit retained).
- **Backups**: `pg_dump` + SeaweedFS volume snapshot, documented in `docs/backup-restore.md`.
- **Regulatory readiness** (not compliance): data minimisation, purpose limitation fields, audit trail, human oversight gates, retention, export — mapped as controls in `docs/compliance-readiness.md`.

## 7. Libraries and licences

See [`licenses.md`](licenses.md). Policy: allow Apache-2.0, MIT, BSD, PostgreSQL, ISC, MPL-2.0 (unmodified, flagged); block GPL/AGPL/SSPL/BUSL and "open-weights" models with custom licences. CI job runs `pip-licenses` and `license-checker` and fails on non-allowlisted licences.

Points that need attention (verified at build time, not assumed):
- **Keycloak** (Apache-2.0), **SeaweedFS** (Apache-2.0), **Valkey** (BSD-3, Redis ≥7.4 is *not* acceptable), **Caddy** (Apache-2.0), **Podman** (Apache-2.0), **GitLab CE** (MIT).
- **Qwen3-8B**: Apache-2.0 weights; confirm on the model card at download time (`scripts/fetch-models.sh` records the commit hash and license file).
- **WeasyPrint** (BSD-3) for PDF. **ECharts** (Apache-2.0). **shadcn/ui** (MIT). **Lucide** (ISC).
- **Celery** (BSD-3). **psycopg** is LGPL-3 → flagged: used as an unmodified dynamically-linked library; alternative `asyncpg` (Apache-2.0) is preferred for the API. Decision: `asyncpg` for API, `psycopg` avoided.
- **Alembic/SQLAlchemy** MIT, **FastAPI** MIT, **Pydantic** MIT, **vLLM** Apache-2.0, **llama.cpp** MIT.

## 8. As built: where the implementation differs from the plan

- **Evaluation code lives inside the API package** (`apps/api/medguard_api/evaluation/`: `adapters`, `ssrf`, `deterministic`, `judge`, `scoring`, `agreement`) instead of a top-level `evaluation/` package: the API and the worker ship as one image and share models. `evaluation/test_suites/` at the repo root holds the synthetic suite data.
- **Tests** live in `apps/api/tests` (unit + integration against real PostgreSQL, a real demo assistant process, a stub judge server) and `tests/e2e` (Playwright). `tests/integration` is therefore not a separate tree.
- **Workers** are the same image running `celery -A medguard_api.worker worker` (`workers/` is not a separate package).
- **Evidence** is written to SeaweedFS (S3 API) with its SHA-256 recorded in PostgreSQL and re-verified on every read; `run_items.response_text` keeps a copy for the UI and is subject to the same retention purge.
- **Metrics** use `prometheus-client` (`/metrics`, not exposed through Caddy); **tracing** uses OpenTelemetry, opt-in via `OTEL_EXPORTER_OTLP_ENDPOINT`.
- **Roles** are not a pure hierarchy: medical validation, reviews, arbitration, release decisions, retention and tokens use exact-role checks (`require_roles`) so that an engineer cannot inherit a reviewer's or an admin's duty.
- **Dependencies added after Phase 1**: `boto3` (S3 client, Apache-2.0), `jinja2`, `weasyprint` (PDF, BSD-3; pulls `pyphen`, see licences), `prometheus-client`, OpenTelemetry SDK/instrumentation, `redis` (MIT client for Celery's Valkey transport).

## 9. Known limitations

- LLM judges are noisy and can share biases with the evaluated model. `GET /api/v1/judge/agreement` measures judge-vs-human agreement (Cohen's kappa) on reviewed cases and states when there are fewer than 30, in which case scores are indicative only. See [evaluation-limits.md](evaluation-limits.md).
- The consistency-across-rephrasings judge criterion is declared but not yet implemented as a multi-prompt check.
- CPU inference of a quantised Qwen3-8B is slow; see [deployment.md](deployment.md).
- The GPU (vLLM) path is configured but has not been exercised in the development environment.
- One organisation per Keycloak user (claim `org`). No self-service organisation management UI.
