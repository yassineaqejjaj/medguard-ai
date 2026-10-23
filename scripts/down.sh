#!/usr/bin/env bash
# Usage: scripts/down.sh [--volumes]   (--volumes ALSO DELETES all data: database, evidence, queue)
source "$(dirname "$0")/_compose.sh"
args=(); [[ "${1:-}" == "--volumes" ]] && args+=(-v)
"${COMPOSE[@]}" --profile demo --profile monitoring --profile cpu --profile gpu down "${args[@]}"
