#!/usr/bin/env bash
# Backs up PostgreSQL (logical dump) and the SeaweedFS evidence volume into ./backups/<timestamp>/.
# Keep .env (secrets, especially MEDGUARD_SECRET_KEY_B64) with the backup, stored separately and encrypted.
source "$(dirname "$0")/_compose.sh"
set -euo pipefail
dir="backups/$(date -u +%Y%m%dT%H%M%SZ)"; mkdir -p "$dir"
"${COMPOSE[@]}" exec -T postgres pg_dump -U medguard -Fc medguard > "$dir/medguard.pgdump"
"${COMPOSE[@]}" exec -T seaweedfs tar -C /data -cf - . > "$dir/evidence.tar"
( cd "$dir" && shasum -a 256 medguard.pgdump evidence.tar > SHA256SUMS )
echo "Backup written to $dir"; ls -lh "$dir"
