#!/usr/bin/env bash
# Creates .env with freshly generated secrets. Never overwrites an existing file.
set -euo pipefail
cd "$(dirname "$0")/.."
if [[ -f .env ]]; then echo ".env already exists; leaving it untouched."; exit 0; fi
rnd() { openssl rand -hex "$1"; }
cat > .env <<ENV
POSTGRES_PASSWORD=$(rnd 16)
MEDGUARD_APP_DB_PASSWORD=$(rnd 16)
MEDGUARD_SECRET_KEY_B64=$(openssl rand -base64 32)
KEYCLOAK_ADMIN_PASSWORD=$(rnd 16)
SEAWEED_S3_ACCESS_KEY=$(rnd 8)
SEAWEED_S3_SECRET_KEY=$(rnd 16)
MEDGUARD_PUBLIC_ADDR=localhost:8443
ENV
chmod 600 .env
echo "Created .env (mode 600). Keep it out of version control and back it up: losing MEDGUARD_SECRET_KEY_B64 makes stored endpoint credentials unreadable."
