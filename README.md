# MedGuard AI

[![CI](https://github.com/yassineaqejjaj/medguard-ai/actions/workflows/ci.yml/badge.svg)](https://github.com/yassineaqejjaj/medguard-ai/actions/workflows/ci.yml)

**Trust every AI decision. Prove every result.**

An open-source *AI assurance platform for healthcare*. MedGuard connects the AI applications a health-tech team builds (assistants and
RAG systems for document search, drafting and administrative help), runs synthetic test campaigns against them, measures quality and
risk, sends doubtful or critical results to qualified human reviewers, blocks versions that fail critical criteria, and keeps the
evidence of every decision.

> **MedGuard does not issue a medical or regulatory certification.** A PASS means a version met the criteria configured for its
> campaign. It is not a guarantee of clinical safety and does not replace medical experts. Everything in this repository runs on
> synthetic data.

![Overview](docs/screenshots/01-overview.png)

## Contents

- [What it does](#what-it-does) · [See it work](#see-it-work) · [Quick start](#quick-start)
- [How it works](#how-it-works) · [Architecture](#architecture) · [Technology](#technology)
- [Trust model](#trust-model-what-keeps-a-score-from-being-mistaken-for-safety) · [Security](#security) · [Testing](#testing)
- [Project status and limits](#project-status-and-limits) · [Documentation](#documentation) · [Licence](#licence)

## What it does

| You want to | MedGuard gives you |
|---|---|
| Register the AI applications under evaluation | An **AI System Registry**: purpose, owner, model, versions, each with its own HTTP test endpoint and encrypted credentials |
| Describe what "correct" means | **Test Studio**: scenarios with category, input, reference document, expected behaviour, severity and pass conditions; versioned, duplicable, orderable; JSON and CSV import and export |
| Test automatically | An **evaluation engine**: workers call your application and apply deterministic checks (JSON, citations, exact rules, limits, latency, leaked identifiers) plus a local **LLM judge** (Qwen3-8B) |
| See quality and risk | **Overview** with pass rate, critical failures, trend by release, failures by severity, pending reviews, and **Results** with the evidence for every scenario |
| Involve medical experts | **Human Reviews**: a queue of flagged cases (critical first), reviewer decisions with annotated errors and justification, disagreement handling and arbitration |
| Compare releases | **Version Comparison**: regressions, fixes, category deltas; a critical regression is never offset by a better average |
| Stop a bad release | **Release Gates**: blocking criteria per application, status PASS, FAIL or REVIEW REQUIRED, a CI/CD status endpoint, and a recorded human release decision |
| Prove what happened | **Evidence Center**: HTML, JSON and PDF reports with integrity hashes, hash-verified stored responses, a tamper-evident audit trail |

Roles: **Admin**, **Engineer**, **Reviewer**, **Viewer**, from your identity provider (Keycloak, OIDC). Each organisation's data is isolated.

## See it work

The demonstration is a fictional RAG assistant in two versions: **v1.0.0** behaves, **v1.1.0** ships deliberate regressions (a
citation to a section that does not exist, an invented dosage, a leaked system prompt, an echoed patient identifier, legal advice,
hallucination on uncovered topics, one slow answer). The same 20 synthetic scenarios run against both.

| | |
|---|---|
| ![AI Systems](docs/screenshots/02-ai-systems.png) **AI Systems.** Applications and their versions. | ![Test Studio](docs/screenshots/04-test-studio.png) **Test Studio.** Versioned scenarios with severity and judge criteria. |
| ![Evaluation Runs](docs/screenshots/05-evaluation-runs.png) **Evaluation Runs.** Campaigns, pass rate, critical failures, flagged results. | ![Results](docs/screenshots/06-evaluation-results.png) **Results.** Failures first, critical before the rest, evidence per scenario. |
| ![Human Review](docs/screenshots/07-human-review.png) **Human Reviews.** Queue, evidence, decision with annotations; judge-versus-human agreement. | ![Comparison](docs/screenshots/08-version-comparison.png) **Version Comparison.** 3 new critical regressions: v1.1.0 is worse whatever the average says. |
| ![Gate FAIL](docs/screenshots/09-release-gate-fail.png) **Release Gate, FAIL.** Blocking criteria, critical tests, human review state; release cannot be signed. | ![Gate PASS](docs/screenshots/10-release-gate-pass.png) **Release Gate, PASS.** Every criterion met and every flagged result reviewed; an admin signs the release. |
| ![Evidence Center](docs/screenshots/11-evidence-center.png) **Evidence Center.** Reports with manifest hashes, stored evidence. | ![Audit trail](docs/screenshots/12-audit-trail.png) **Audit trail.** Hash chain verified; every review and release decision recorded. |

Dark mode is supported ([screenshot](docs/screenshots/14-overview-dark.png)). Settings (retention, CI tokens):
[screenshot](docs/screenshots/13-settings.png). Screenshots are generated from the running application by
`tests/e2e/screenshots.spec.ts`.

## Quick start

Requires Docker (or Podman with `podman compose`), about 8 GB of RAM, and `openssl`.

```bash
git clone <this repository> && cd medguard-ai
scripts/init-env.sh            # generates .env with random secrets
scripts/up.sh --demo --http    # builds and starts everything (plain HTTP on localhost, development only)
scripts/seed-demo.sh           # loads the synthetic demo
```

Open <http://localhost:8443>, sign in as `engineer@demo.test` / `demo-engineer` (also `reviewer@demo.test`, `admin@demo.test`,
`viewer@demo.test`; passwords are `demo-<role>`; **demo users only**, see [deployment](docs/deployment.md)), then:
**Evaluation Runs, New evaluation run**, pick `Demo Clinical Assistant · v1.0.0` and the demo suite, and repeat for `v1.1.0`.
Open the results, review the critical failures as the reviewer, compare the two versions, evaluate the gate as the engineer, and
sign off (or block) as the admin. API docs: <http://localhost:8443/api/docs>.

Optional: `--monitoring` (Prometheus, OpenTelemetry collector), `--cpu` or `--gpu` for the judge model
(`scripts/fetch-models.sh` first). Stop with `scripts/down.sh`.

## How it works

```mermaid
flowchart LR
  E[Engineer] -->|launch campaign| API
  API -->|enqueue| Q[(Valkey)]
  Q --> W[Worker]
  W -->|HTTP, SSRF-guarded| APP[Application under test]
  W -->|responses + SHA-256| S3[(SeaweedFS)]
  W --> DET[Deterministic checks]
  W --> J[LLM judge<br/>Qwen3-8B, local]
  DET & J --> POL[Review policy]
  POL -->|flagged or critical| R[Reviewer]
  POL & R --> G[Release gate]
  G -->|PASS / FAIL / REVIEW REQUIRED| CI[CI/CD]
  G -->|signed decision| A[Admin]
  API --> PG[(PostgreSQL<br/>row-level security)]
  G & R & A --> EV[Reports + audit chain]
```

1. An engineer launches a **run** of a suite against an application version. The run pins the exact scenario versions it will execute.
2. A **worker** calls the application's endpoint through the HTTP adapter (timeout, size cap, no redirects, internal addresses blocked).
3. **Deterministic checks** run first. **Judge criteria** then run on a local model with fixed parameters and a versioned prompt.
4. The **review policy** decides the result and whether a human must look (below).
5. Reviewers record decisions; disagreements wait for an admin to arbitrate.
6. The **gate** evaluates blocking criteria independently of averages and returns PASS, FAIL or REVIEW REQUIRED; CI reads it with a token.
7. An authorised admin **signs off** or blocks. A release cannot be signed while the gate is not PASS.
8. **Reports** and the **audit trail** tie the decision to the run, scenario versions, settings, model and prompt versions, and people.

## Architecture

A modular monolith, deliberately simple: one frontend, one API, workers (same image), one database and the supporting services.

| Layer | Choice |
|---|---|
| Frontend | Next.js (App Router), React, TypeScript, Tailwind CSS, Lucide, Apache ECharts |
| API | Python, FastAPI, Pydantic, SQLAlchemy 2 (async, asyncpg), Alembic |
| Data | PostgreSQL 17 with **row-level security**; SeaweedFS (S3 API) for evidence and reports |
| Queue and workers | Valkey, Celery |
| Judge model | Qwen3-8B (Apache-2.0) served by llama.cpp (CPU) or vLLM (GPU) through an OpenAI-compatible endpoint; no hosted service |
| Identity | Keycloak, OpenID Connect, authorization code with PKCE |
| Edge | Caddy (TLS, reverse proxy) |
| Observability | Prometheus metrics, OpenTelemetry traces (opt-in) |
| Tests | pytest, Vitest, Playwright |
| Packaging | OCI images, Compose (works with Podman or Docker), GitLab CI and GitHub Actions |

Every component is open source (OSI-approved licence) and self-hostable; the whole platform can run isolated once images and the model are
downloaded. The full data model, API and decisions are in [docs/architecture.md](docs/architecture.md); the inventory of licences, with
the exceptions recorded, is in [docs/licenses.md](docs/licenses.md).

```text
apps/api/        FastAPI, models, migrations, evaluation engine, worker, tests
apps/web/        Next.js application
apps/demo-assistant/   fictional assistant (v1 good, v2 regressed)
evaluation/test_suites/  synthetic scenarios
infrastructure/  Keycloak realm, Caddy, Prometheus, OTel collector
tests/e2e/       Playwright journey and screenshots
scripts/         up, down, seed, backup, restore, models, licences, CI gate helper
docs/            architecture, deployment, API, security, limits, compliance readiness
```

## Trust model: what keeps a score from being mistaken for safety

- **A judge never decides alone.** A deterministic failure fails the result whatever the judge says; a judge pass cannot override it.
- **Humans are routed in** for critical failures, low judge confidence (< 0.7), judge errors, judge/deterministic disagreement, and
  high-severity passes backed by a judge verdict alone. A critical failure always needs an explicit human decision.
- **A result's score is its weakest criterion**, not an average. **The gate checks critical failures independently**: 99 passes and one
  critical failure is a FAIL.
- **The release decision is human.** The gate informs it; an admin signs it, under their name, with a justification, immutably.
- **Reproducibility.** Judge temperature 0, seed 42, fixed token limit, versioned prompt; model name, digest and prompt version stored on
  every run; scenarios are immutable per version; gate policy is snapshotted into each evaluation.
- **The judge is measured against people.** Agreement with human decisions (Cohen's kappa, false-pass count) is computed from reviewed
  cases and flagged as indicative below 30 cases. See [docs/evaluation-limits.md](docs/evaluation-limits.md).

## Security

Tenant isolation by PostgreSQL row-level security (and again in the API), exact-role checks for duties an engineer must not inherit,
AES-256-GCM for stored credentials, SSRF protection with IP pinning for outbound calls, strict input validation, escaped and sandboxed
reports, a hash-chained insert-only audit log, hash-verified evidence, rate limiting, and non-root containers. Details, the tests that
cover each control, and the gaps (no pen test, demo credentials, `start-dev` Keycloak in Compose) are in [docs/security.md](docs/security.md).
Technical measures towards GDPR, HDS and AI Act work are listed in [docs/compliance-readiness.md](docs/compliance-readiness.md); the product
is not presented as compliant.

## Testing

| Suite | What | Count at last run |
|---|---|---|
| `apps/api/tests` (pytest) | tenant isolation on a real PostgreSQL, auth and roles, scenarios and import/export, engine against a **real** demo assistant process, SSRF guard, scoring policy, judge client (stub server), reviews, comparison, gates, CI tokens, reports, retention, rate limiting, agreement | 90 passed, 1 skipped (PDF needs Pango; verified in the container image) |
| `apps/web` (Vitest, ESLint, build) | formatting and navigation helpers; lint; production build | 7 tests |
| `tests/e2e` (Playwright, real browser, real stack) | the full demonstration journey through the UI: connect an assistant, import 20 scenarios, run two versions, review, compare, gate, sign off, report, audit, tenant and role boundaries | 5 passed |

Dependency checks: `pip-audit` and `pnpm audit --prod` clean on 2026-10-22; `scripts/check_licenses.py` enforces the licence policy.
See [docs/development.md](docs/development.md) to run them.

## Project status and limits

This is an MVP intended for health-tech pilots, not a finished product. Stated plainly:

| Area | State |
|---|---|
| Registry, Test Studio, engine, runs, results, dashboard, reviews, comparison, gates, evidence, settings, CI endpoint | Implemented and covered by tests and the end-to-end journey |
| **LLM judge with the real Qwen3-8B** | Client, prompt, policy and deployment configuration are implemented and tested against a stub server. **It has not been run against the real model in this repository's test environment.** Without a judge configured, judge criteria go to human review. |
| GPU path (vLLM) | Configured in Compose, never exercised here |
| Podman | Compose file and scripts support it; only Docker was used during development |
| Consistency across rephrasings | Declared as a criterion, not yet a multi-prompt check |
| CI | GitHub Actions runs the API tests (including the PDF test), the web checks and the licence policy: green. `.gitlab-ci.yml` is written for self-hosted GitLab CE but has not been run on a GitLab instance |
| Evidence restore | Database restore rehearsed; evidence archive restore not rehearsed |
| Production readiness | See the hardening checklist in [docs/deployment.md](docs/deployment.md) |

## Documentation

[Architecture](docs/architecture.md) · [Deployment and hardware](docs/deployment.md) · [API](docs/api.md) ·
[Security](docs/security.md) · [Evaluation limits](docs/evaluation-limits.md) · [Compliance readiness](docs/compliance-readiness.md) ·
[Backup and restore](docs/backup-restore.md) · [Licences](docs/licenses.md) · [Development](docs/development.md)

## Licence

[Apache License 2.0](LICENSE). Third-party components keep their own licences, listed in [docs/licenses.md](docs/licenses.md).
