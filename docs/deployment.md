# Deployment

## Requirements

| | Minimum (demo, no judge) | With CPU judge (Qwen3-8B Q4_K_M) | With GPU judge (vLLM) |
|---|---|---|---|
| CPU | 4 cores | 8+ cores | 4+ cores |
| RAM | 8 GB | 16 GB (the model needs about 6 GB) | 16 GB |
| Disk | 10 GB | 20 GB (the model file is 5.0 GB) | 40 GB (FP16 weights are about 16 GB) |
| GPU | none | none | NVIDIA, 16 GB VRAM or more for FP16 (less with a quantised model) |

**CPU limits.** A quantised 8B model on CPU generates only a few tokens per second. Each judge criterion is one call of up to
700 output tokens, so a campaign with many judge criteria takes minutes to tens of minutes. Use CPU mode for demos and small
suites; use a GPU for real campaigns. Deterministic checks need no model and finish in seconds.

## First start

```bash
scripts/init-env.sh            # generates .env with random secrets (never commit it)
scripts/up.sh --demo --http    # build and start; --http serves plain HTTP on http://localhost:8443 (local development only)
scripts/seed-demo.sh           # load the synthetic demo (1 application, 2 versions, 20 scenarios)
```

Open `http://localhost:8443` and sign in with a demo user from the Keycloak realm
(`infrastructure/compose/keycloak/medguard-realm.json`). **These are demo passwords: change or delete them for any real use.**

| User | Role |
|---|---|
| admin@demo.test | admin |
| engineer@demo.test | engineer |
| reviewer@demo.test | reviewer |
| viewer@demo.test | viewer |
| other-admin@other.test | admin of a second organisation (isolation tests) |

Without `--http`, Caddy serves HTTPS on `https://localhost:8443` with its internal CA (browsers warn until you trust it).
In production set `MEDGUARD_PUBLIC_ADDR` to your hostname so Caddy obtains a public certificate.

Stop with `scripts/down.sh` (keeps data) or `scripts/down.sh --volumes` (**deletes all data**).

Podman: `scripts/*.sh` use `podman compose` when it is available and `docker compose` otherwise. The images are standard OCI
images and `compose.yaml` is plain Compose. This repository was developed and tested with Docker; Podman has not been run.

## The judge model

```bash
scripts/fetch-models.sh                 # asks before downloading 5.0 GB; verifies a pinned SHA-256; writes a manifest
scripts/up.sh --http --cpu              # starts llama.cpp serving Qwen3-8B on the compose network
```

Then set in `.env`: `MEDGUARD_JUDGE_URL=http://llm-cpu:8080` and `MEDGUARD_JUDGE_MODEL_DIGEST=sha256:...` (printed by the script),
and restart the worker. For GPU: `scripts/up.sh --gpu` and `MEDGUARD_JUDGE_URL=http://llm-gpu:8080`
(set `VLLM_IMAGE` to a vLLM tag you have validated; it downloads `Qwen/Qwen3-8B` on first start).

With no judge configured the platform still works: judge criteria are recorded as errors and the result is routed to a human.

## Air-gapped operation

Once images are built, the model file is downloaded and dependencies are baked into the images, nothing contacts the internet at
run time (fonts are bundled at build time by `next/font`). Build on a connected machine and move the images with
`podman save` / `docker save`.

## Production hardening checklist

- [ ] Real hostname in `MEDGUARD_PUBLIC_ADDR`, HTTPS on. Keycloak behind TLS, started with `start` (not `start-dev`) and an external database.
- [ ] Remove the demo realm users and `other-org`; create real users and map them to the four realm roles.
- [ ] Set `MEDGUARD_ALLOW_PRIVATE_TARGETS=false` on the worker (the compose default is `true` only so the demo assistants are reachable).
- [ ] Strong, unique values in `.env`; keep `MEDGUARD_SECRET_KEY_B64` in a secret manager and back it up separately from the data.
- [ ] Do not publish ports 5432, 6379, 8333 or Keycloak's admin console beyond a private network.
- [ ] Schedule `scripts/backup.sh` and rehearse `scripts/restore.sh` ([backup-restore.md](backup-restore.md)).
- [ ] Set the organisation retention period and schedule the purge (Settings, or `POST /api/v1/settings/retention/purge`).
- [ ] Pin image tags or digests you have validated (the judge server images are not pinned).
- [ ] Use synthetic or properly de-identified data only, unless a separate data-protection assessment covers real data.
