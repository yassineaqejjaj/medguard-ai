#!/usr/bin/env bash
# CI/CD helper: prints the release-gate status of an application version and exits with a pipeline-friendly code.
#   0 PASS · 1 FAIL · 2 REVIEW_REQUIRED · 3 NOT_EVALUATED · 4 error talking to MedGuard
# Usage: MEDGUARD_TOKEN=mgt_... scripts/medguard-gate.sh --url https://medguard.example --system "My assistant" --version v1.2.0
set -uo pipefail
url="" system="" version=""
while [[ $# -gt 0 ]]; do case "$1" in --url) url="$2"; shift 2;; --system) system="$2"; shift 2;; --version) version="$2"; shift 2;; *) echo "unknown option $1" >&2; exit 4;; esac; done
[[ -n "$url" && -n "$system" && -n "$version" && -n "${MEDGUARD_TOKEN:-}" ]] || { echo "need --url --system --version and MEDGUARD_TOKEN" >&2; exit 4; }
resp="$(curl -fsS --get "$url/api/v1/ci/gate" --data-urlencode "system=$system" --data-urlencode "version=$version" \
        -H "Authorization: Bearer $MEDGUARD_TOKEN")" || { echo "request failed" >&2; exit 4; }
python3 - "$resp" <<'PY'
import json, sys
r = json.loads(sys.argv[1])
print(f"{r['status']}  (exit {r['exit_code']})")
for reason in r.get("reasons", []): print(f"  - {reason}")
print(r.get("note", ""))
sys.exit(r["exit_code"])
PY
