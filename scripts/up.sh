#!/usr/bin/env bash
# Usage: scripts/up.sh [--demo] [--monitoring] [--cpu|--gpu] [--http]
#   --demo        also start the two fictional demo assistants
#   --monitoring  Prometheus + OpenTelemetry collector
#   --cpu / --gpu judge model server (llama.cpp on CPU, vLLM on GPU); needs the model, see scripts/fetch-models.sh
#   --http        plain HTTP on http://localhost:8443 (no self-signed certificate); local development only
source "$(dirname "$0")/_compose.sh"
[[ -f .env ]] || "$ROOT/scripts/init-env.sh"
profiles=()
for a in "$@"; do
  case "$a" in
    --demo) profiles+=(--profile demo);; --monitoring) profiles+=(--profile monitoring);;
    --cpu) profiles+=(--profile cpu);; --gpu) profiles+=(--profile gpu);;
    --http) export MEDGUARD_PUBLIC_ADDR=http://localhost:8443 MEDGUARD_TLS_DIRECTIVE=log;;
    *) echo "unknown option $a" >&2; exit 1;;
  esac
done
"${COMPOSE[@]}" "${profiles[@]}" up -d --build
echo "MedGuard is starting. Open ${MEDGUARD_PUBLIC_ADDR:-https://localhost:8443}  (Keycloak: http://localhost:8080)"
