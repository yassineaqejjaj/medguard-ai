# Development

## Layout

```text
apps/api/medguard_api/   FastAPI app, models, security, routers, evaluation engine, Celery worker
apps/api/migrations/     Alembic (0001 schema, 0002 RLS and grants, 0003 CI token lookup)
apps/api/tests/          pytest: unit + integration (real PostgreSQL, real demo assistant processes, stub judge server)
apps/web/                Next.js (App Router), Tailwind, ECharts, oidc-client-ts; Vitest
apps/demo-assistant/     Fictional RAG assistant (v1 behaves, v2 has deliberate regressions)
evaluation/test_suites/  Synthetic 20-scenario suite (copy shipped in apps/api/suites for the seed script)
infrastructure/          Keycloak realm, Caddyfile, Prometheus and OTel collector configs
tests/e2e/               Playwright: demo journey and README screenshots
scripts/                 up/down/seed/backup/restore, model fetch, licence checks, CI gate helper
docs/                    this documentation
```

## Run the tests

```bash
# API: needs a PostgreSQL superuser reachable on localhost:55432 (the suite migrates it itself)
docker run -d --rm --name mg-pg -e POSTGRES_USER=medguard -e POSTGRES_PASSWORD=medguard -e POSTGRES_DB=medguard -p 55432:5432 postgres:17-alpine
cd apps/api && uv sync && uv run pytest -q

# Web
cd apps/web && pnpm install && pnpm lint && pnpm test && pnpm build

# End to end (stack running with scripts/up.sh --demo --http, then scripts/seed-demo.sh for the screenshots)
cd tests/e2e && pnpm install && pnpm test          # uses your installed Chrome; no browser download
cd tests/e2e && pnpm screenshots                   # regenerates docs/screenshots on a fresh seeded stack

# Policy
python3 scripts/check_licenses.py
```

The PDF test is skipped on machines without Pango; PDF rendering is verified inside the API container image.

## Conventions

- Every tenant table has `org_id` and a row-level-security policy; new tables must add both in a migration (`0002` shows the pattern).
- Immutable or append-only facts (scenario versions, reviews, release decisions, gate evaluations, audit log) are never updated.
- A new check on application output belongs in `evaluation/deterministic.py` with a unit test; anything that decides a verdict
  belongs in `evaluation/scoring.py`.
- No external SaaS and no proprietary model: `scripts/check_licenses.py` must stay green.
