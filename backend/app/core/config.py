from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict

REPO_ROOT_ENV = Path(__file__).resolve().parents[3] / ".env"


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=str(REPO_ROOT_ENV),
        extra="ignore",
    )

    database_url: str
    migration_database_url: str
    app_secret_key: str

    # Field-level encryption / blind-index keys (Section 7.4). Not yet
    # used by any Phase 1 table — complainant identity encryption is
    # Phase 3 (case_parties). Kept here so the key-rotation job design
    # (Phase 1 gate) has a real key to rotate.
    identifier_encryption_key: str
    identifier_fingerprint_key: str

    access_token_ttl_minutes: int = 15
    refresh_token_ttl_days: int = 7
    step_up_ttl_minutes: int = 5

    # Section 4.1: 5 failures / 10 minutes, configurable later via admin
    # console (Phase 2+) — hardcoded default for now.
    lockout_threshold: int = 5
    lockout_window_minutes: int = 10

    totp_issuer: str = "CaseMesh (AICTE)"

    web_origin: str = "http://localhost:3001"
    valkey_url: str = "redis://localhost:6379/0"

    # Dev/CI runs over plain HTTP; Caddy terminates real TLS in Phase 9.
    # Cookies are Secure=false only when this is explicitly false.
    cookies_secure: bool = False

    # Section 13: Sentry. Absent DSN means disabled — same honest
    # pattern every adapter uses (Section 3): never a fake "configured".
    sentry_dsn: str | None = None

    # Section 1.4(b): this deployment shows TEST DATA, not real AICTE
    # data (user decision, docs/decision-log.md Phase 2). Drives a
    # permanent red banner on every screen and export. Flip to False
    # only when this instance is pointed at a real, authorised AICTE
    # data source — never silently.
    tenant_mode: str = "test_sandbox"
    app_version: str = "0.1.0"
    project_name: str = "CaseMesh"

    @property
    def is_sandbox_mode(self) -> bool:
        """Return True if current deployment runs in test sandbox mode."""
        return self.tenant_mode == "test_sandbox"

    @property
    def is_sentry_enabled(self) -> bool:
        """Return True if Sentry error reporting DSN is configured."""
        return bool(self.sentry_dsn)



settings = Settings()
