#!/usr/bin/env bash
# Controlled download of the judge model: Qwen3-8B (Apache-2.0), Q4_K_M GGUF for llama.cpp (CPU).
# Pinned to one repository revision and one SHA-256; refuses to keep a file that does not match.
# For GPU, vLLM pulls Qwen/Qwen3-8B itself on first start (see docs/deployment.md).
set -euo pipefail

REPO="Qwen/Qwen3-8B-GGUF"
REV="7c41481f57cb95916b40956ab2f0b139b296d974"
FILE="Qwen3-8B-Q4_K_M.gguf"
SHA256="d98cdcbd03e17ce47681435b5150e34c1417f50b5c0019dd560e4882c5745785"
SIZE=5027783488
DEST="$(cd "$(dirname "$0")/.." && pwd)/models"

if [[ "${1:-}" != "--yes" ]]; then
  printf 'This downloads %s (%.1f GB) from huggingface.co/%s at revision %s.\nLicence: Apache-2.0. Continue? [y/N] ' \
    "$FILE" "$(echo "$SIZE / 1000000000" | bc -l)" "$REPO" "${REV:0:8}"
  read -r ans; [[ "$ans" =~ ^[Yy]$ ]] || { echo "Aborted."; exit 1; }
fi

mkdir -p "$DEST"
URL="https://huggingface.co/$REPO/resolve/$REV"
curl -L --fail --retry 3 -C - -o "$DEST/$FILE" "$URL/$FILE"
curl -L --fail -s -o "$DEST/LICENSE-Qwen3-8B" "$URL/LICENSE"

actual="$(shasum -a 256 "$DEST/$FILE" | cut -d' ' -f1)"
if [[ "$actual" != "$SHA256" ]]; then
  echo "Checksum mismatch: expected $SHA256, got $actual. Deleting the file." >&2
  rm -f "$DEST/$FILE"; exit 2
fi

cat > "$DEST/qwen3-8b.manifest.json" <<JSON
{"repo": "$REPO", "revision": "$REV", "file": "$FILE", "sha256": "$SHA256", "size": $SIZE, "licence": "Apache-2.0",
 "downloaded_at": "$(date -u +%FT%TZ)"}
JSON
echo "OK. Add to .env:  MEDGUARD_JUDGE_MODEL_DIGEST=sha256:$SHA256"
echo "Then: docker compose --profile cpu up -d llm-cpu   and set MEDGUARD_JUDGE_URL=http://llm-cpu:8080"
