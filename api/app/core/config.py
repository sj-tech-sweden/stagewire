from functools import lru_cache

from pydantic import field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
        env_prefix="",
    )

    app_name: str = "Stagewire API"
    app_env: str = "development"
    app_host: str = "0.0.0.0"
    app_port: int = 8010

    # Echo SQL to the logs. Off by default; enable for local debugging only
    # (it is very noisy in the container logs otherwise).
    sql_echo: bool = False

    database_url: str = "postgresql+asyncpg://stagewire:stagewire@localhost:5433/stagewire"
    redis_url: str = "redis://localhost:6380/0"

    cors_origins: str = "http://localhost:9010"

    stockwire_api_base_url: str = "https://rental-api.sj-tech.se"
    stockwire_api_token: str | None = None

    # --- Uploaded files (stage plot element images) ---
    # Directory the API stores uploaded files in. Serve it at /static via a
    # StaticFiles mount. In the container this is backed by a persistent volume.
    upload_dir: str = "/app/uploads"
    # Max upload size in bytes (default 5 MB).
    max_upload_bytes: int = 5 * 1024 * 1024
    # Allowed image extensions (used for the generated filename only).
    upload_extensions: list[str] = [".png", ".jpg", ".jpeg", ".gif", ".webp", ".svg"]

    # --- Auth / JWT ---
    jwt_secret_key: str = "dev-insecure-jwt-secret-change-me-please-rotate-in-prod-8f3a"
    jwt_algorithm: str = "HS256"
    jwt_access_expire_minutes: int = 60
    jwt_refresh_expire_days: int = 30
    jwt_refresh_reuse_grace_seconds: int = 30

    # Where the SPA lives; used for SAML/SSO post-login redirects.
    effective_frontend_base_url: str = "http://localhost:9010"

    # --- SSO (OIDC + SAML) ---
    # Single OIDC provider (env-driven; mirror stockwire-rental's model).
    oidc_enabled: bool = False
    oidc_key: str = "oidc"
    oidc_display_name: str = "Single Sign-On"
    oidc_issuer: str = ""
    oidc_client_id: str = ""
    oidc_client_secret: str = ""
    oidc_authorization_endpoint: str = ""
    oidc_token_endpoint: str = ""
    oidc_jwks_uri: str = ""
    oidc_scopes: str = "openid email profile"
    oidc_email_claim: str = "email"
    oidc_name_claim: str = "name"
    oidc_subject_claim: str = "sub"
    oidc_group_claim: str = "groups"
    oidc_allow_auto_create: bool = True

    # Single SAML provider.
    saml_enabled: bool = False
    saml_key: str = "saml"
    saml_display_name: str = "Single Sign-On (SAML)"
    saml_idp_entity_id: str = ""
    saml_idp_sso_url: str = ""
    saml_idp_x509_cert: str = ""
    saml_sp_entity_id: str = ""
    saml_acs_url: str = ""
    saml_email_attribute: str = "email"
    saml_name_attribute: str = "name"
    saml_subject_attribute: str = "subject"
    saml_group_attribute: str = "groups"
    saml_allow_auto_create: bool = True

    # Global SSO behaviour.
    sso_enabled: bool = False
    sso_auto_create_users: bool = True
    sso_sync_roles_on_login: bool = True
    sso_default_role: str = "viewer"
    # Mapping of IdP group name -> stagewire role, comma-separated "group:role".
    sso_group_role_map: str = ""

    @property
    def sso_group_role_map_dict(self) -> dict[str, str]:
        result: dict[str, str] = {}
        for pair in (self.sso_group_role_map or "").split(","):
            if ":" not in pair:
                continue
            group, role = pair.split(":", 1)
            group = group.strip()
            role = role.strip()
            if group and role:
                result[group] = role
        return result

    @property
    def secure_cookies(self) -> bool:
        return self.app_env.lower() == "production"

    @property
    def cors_origins_list(self) -> list[str]:
        raw = (self.cors_origins or "").strip()
        if not raw:
            return []
        if raw.startswith("["):
            import json

            return [str(item) for item in json.loads(raw)]
        return [origin.strip() for origin in raw.split(",") if origin.strip()]

    @property
    def is_production(self) -> bool:
        return self.app_env.lower() == "production"

    @field_validator("database_url")
    @classmethod
    def _require_async_driver(cls, v: str) -> str:
        # CloudNativePG (and most operators) hand out a bare `postgresql://` URI.
        # SQLAlchemy's asyncio engine needs a genuinely async DBAPI, so rewrite the
        # scheme to the psycopg3 dialect. psycopg2 (sync) is rejected.
        if v.startswith("sqlite") and "+aiosqlite" not in v:
            v = v.replace("sqlite", "sqlite+aiosqlite", 1)
        scheme = v.split(":", 1)[0]
        if scheme in ("postgresql", "postgres"):
            v = v.replace(scheme, "postgresql+psycopg", 1)
        elif scheme == "postgresql+psycopg2":
            v = v.replace("postgresql+psycopg2", "postgresql+psycopg", 1)
        return v


@lru_cache
def get_settings() -> Settings:
    return Settings()
