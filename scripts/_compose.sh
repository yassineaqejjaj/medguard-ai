# Sourced by the other scripts. Prefers Podman, falls back to Docker. Both read the same compose.yaml.
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
if command -v podman >/dev/null 2>&1 && podman compose version >/dev/null 2>&1; then COMPOSE=(podman compose); else COMPOSE=(docker compose); fi
cd "$ROOT"
