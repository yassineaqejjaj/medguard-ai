#!/usr/bin/env bash
# Restores a backup made by backup.sh into the RUNNING stack. DESTRUCTIVE: replaces the current database and evidence.
# Usage: scripts/restore.sh backups/<timestamp> [--database NAME]   (use a scratch NAME to rehearse without touching live data)
source "$(dirname "$0")/_compose.sh"
set -euo pipefail
dir="${1:?backup directory}"; db="medguard"; [[ "${2:-}" == "--database" ]] && db="${3:?name}"
( cd "$dir" && shasum -a 256 -c SHA256SUMS )
if [[ "$db" == "medguard" ]]; then
  read -r -p "This REPLACES the live database and evidence. Type 'restore' to continue: " ok; [[ "$ok" == "restore" ]] || exit 1
  "${COMPOSE[@]}" stop api worker
fi
"${COMPOSE[@]}" exec -T postgres psql -U medguard -d postgres -c "DROP DATABASE IF EXISTS \"$db\";" -c "CREATE DATABASE \"$db\";"
"${COMPOSE[@]}" exec -T postgres pg_restore -U medguard -d "$db" --no-owner --role=medguard < "$dir/medguard.pgdump"
if [[ "$db" == "medguard" ]]; then
  "${COMPOSE[@]}" exec -T seaweedfs sh -c 'rm -rf /data/* ' || true
  "${COMPOSE[@]}" exec -T seaweedfs tar -C /data -xf - < "$dir/evidence.tar"
  "${COMPOSE[@]}" restart seaweedfs; "${COMPOSE[@]}" start api worker
fi
echo "Restore complete into database '$db'."
