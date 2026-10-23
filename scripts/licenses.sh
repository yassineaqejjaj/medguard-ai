#!/usr/bin/env bash
# Regenerates docs/licenses.md from the actual dependency trees (Python, JavaScript) plus the curated image/model list.
set -euo pipefail
cd "$(dirname "$0")/.."
out=docs/licenses.md
{
cat <<'HDR'
# Licence inventory

Policy: every component must be open source under an OSI-approved licence, self-hostable, with no proprietary service
required. Permissive licences are preferred (Apache-2.0, MIT, BSD, ISC, PostgreSQL). `scripts/check_licenses.py` enforces
the allowlist in CI; recorded exceptions are explicit.

## Exceptions and flags (read first)

| Component | Licence | Why it is accepted |
|---|---|---|
| `pyphen` (via WeasyPrint) | GPL-2.0+ / LGPL-2.1+ / **MPL-1.1** (tri-licence) | Used under MPL-1.1, unmodified. Replace WeasyPrint to remove it. |
| `certifi` | MPL-2.0 | CA bundle, unmodified; file-level weak copyleft. |
| `caniuse-lite` | CC-BY-4.0 (data, **not OSI**) | Build-time browser-support data pulled in by Next.js; not present in the runtime image. |
| Base container images | Debian/Alpine packages (GPL etc.) | Distribution userland, not linked into MedGuard code. Review per image before redistributing images. |
| `psycopg` (LGPL) | none | **Deliberately not used**: the API uses `asyncpg` (Apache-2.0). |
| Redis 7.4+ server | RSALv2/SSPL (**not OSI**) | **Deliberately not used**: the queue is Valkey (BSD-3-Clause). The Python client is `redis-py` (MIT), which speaks the same protocol. |

## Services and model (container images / weights)

| Component | Version pinned | Licence |
|---|---|---|
| PostgreSQL | 17 | PostgreSQL License |
| Valkey | 8 | BSD-3-Clause |
| Keycloak | 26.0 | Apache-2.0 |
| SeaweedFS | 3.80 | Apache-2.0 |
| Caddy | 2 | Apache-2.0 |
| Prometheus | 2.55.1 | Apache-2.0 |
| OpenTelemetry Collector | 0.114.0 | Apache-2.0 |
| llama.cpp (CPU judge server) | `server` tag | MIT |
| vLLM (GPU judge server) | `VLLM_IMAGE` | Apache-2.0 |
| **Qwen3-8B** (judge model) | GGUF repo revision `7c41481f` | **Apache-2.0** (verified in the Hugging Face model metadata: `license: apache-2.0`) |
| Inter, JetBrains Mono (fonts via `next/font`) | n/a | SIL Open Font License 1.1 (OSI-approved) |

## Python (API and worker): resolved dependency tree
HDR
echo
(cd apps/api && uv run pip-licenses --format=markdown --with-urls --order=license)
echo
echo "## JavaScript (web, production dependencies)"
echo
echo "| Package | Version | Licence |"; echo "|---|---|---|"
(cd apps/web && pnpm licenses list --prod --json | python3 -c "
import json,sys
for lic,pk in sorted(json.load(sys.stdin).items()):
    for p in pk: print(f\"| {p['name']} | {', '.join(p['versions'])} | {lic} |\")")
echo
echo "_Generated $(date +%F). Development-only tooling (Vitest, ESLint, Playwright, pytest) is not shipped._"
} > "$out"
echo "wrote $out"
