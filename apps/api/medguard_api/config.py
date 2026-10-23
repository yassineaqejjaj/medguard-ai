from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="MEDGUARD_", env_file=".env", extra="ignore")

    database_url: str = "postgresql+asyncpg://medguard_app:medguard_app@localhost:5432/medguard"
    valkey_url: str = "redis://localhost:6379/0"
    oidc_issuer: str = "http://localhost:8080/realms/medguard"
    oidc_audience: str = "medguard-api"
    oidc_jwks_url: str | None = None
    org_claim: str = "org"
    secret_key_b64: str = ""  # 32 bytes, base64; AES-256-GCM key for stored secrets
    allow_private_targets: bool = False
    auth_dev_bypass: bool = False  # tests/local only; never enable in production
    rate_limit_per_minute: int = 300
    rate_limit_backend: str = "valkey"  # "valkey" or "memory" (tests / single-process dev)
    judge_url: str | None = None  # OpenAI-compatible server (vLLM / llama.cpp) running Qwen3-8B
    judge_model: str = "Qwen/Qwen3-8B"
    judge_model_digest: str | None = None  # commit hash / sha256 recorded by scripts/fetch-models.sh
    judge_api_key: str | None = None
    run_concurrency: int = 4
    evidence_backend: str = "s3"  # "s3" (SeaweedFS) or "memory" (tests only)
    s3_endpoint: str = "http://localhost:8333"
    s3_access_key: str = ""
    s3_secret_key: str = ""
    s3_bucket: str = "medguard-evidence"


@lru_cache
def get_settings() -> Settings:
    return Settings()
