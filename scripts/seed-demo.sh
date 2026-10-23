#!/usr/bin/env bash
# Loads synthetic demo data into the demo organisation: one application with two versions (v1.0.0 behaves, v1.1.0 has
# deliberate regressions) and a 20-scenario suite. Start the stack with --demo first. Idempotent.
source "$(dirname "$0")/_compose.sh"
"${COMPOSE[@]}" run --rm migrate python -m medguard_api.seed_demo demo-org \
  http://demo-assistant-v1:9000/ask http://demo-assistant-v2:9000/ask
