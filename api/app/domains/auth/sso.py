from __future__ import annotations

import base64
import hashlib
import hmac
import json
import secrets
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any
from urllib.parse import urlparse

import httpx
import jwt
from fastapi import HTTPException, status
from jwt.algorithms import ECAlgorithm, RSAAlgorithm
from onelogin.saml2.auth import OneLogin_Saml2_Auth
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.domains.auth.models import AppSetting, Role, User
from app.domains.auth.schemas import SSOProviderSummary
from app.domains.auth.security import hash_password

settings = get_settings()

VALID_ROLES = {"admin", "manager", "viewer"}
_ROLE_PRIORITY = {"admin": 3, "manager": 2, "viewer": 1}
_OIDC_STATE_EXPIRY_SECONDS = 300


@dataclass
class OIDCProvider:
    key: str
    display_name: str
    issuer: str
    client_id: str
    client_secret: str
    authorization_endpoint: str
    token_endpoint: str
    jwks_uri: str
    scopes: str
    group_claim: str
    email_claim: str
    name_claim: str
    subject_claim: str
    allow_auto_create: bool
    enabled: bool


@dataclass
class SAMLProvider:
    key: str
    display_name: str
    idp_entity_id: str
    idp_sso_url: str
    idp_x509_cert: str
    sp_entity_id: str
    acs_url: str
    group_attribute: str
    email_attribute: str
    name_attribute: str
    subject_attribute: str
    allow_auto_create: bool
    enabled: bool


@dataclass
class SSORuntimeConfig:
    enabled: bool
    auto_create_users: bool
    sync_roles_on_login: bool
    default_role: str
    group_role_map: dict[str, str]
    oidc_providers: dict[str, dict[str, Any]]
    saml_providers: dict[str, dict[str, Any]]


def _oidc_provider_from_dict(key: str, raw: dict[str, Any]) -> OIDCProvider:
    return OIDCProvider(
        key=key,
        display_name=raw.get("display_name") or key,
        issuer=raw.get("issuer") or "",
        client_id=raw.get("client_id") or "",
        client_secret=raw.get("client_secret") or "",
        authorization_endpoint=raw.get("authorization_endpoint") or "",
        token_endpoint=raw.get("token_endpoint") or "",
        jwks_uri=raw.get("jwks_uri") or "",
        scopes=raw.get("scopes") or "openid email profile",
        group_claim=raw.get("group_claim") or "groups",
        email_claim=raw.get("email_claim") or "email",
        name_claim=raw.get("name_claim") or "name",
        subject_claim=raw.get("subject_claim") or "sub",
        allow_auto_create=bool(raw.get("allow_auto_create", False)),
        enabled=bool(raw.get("enabled", True)),
    )


def _saml_provider_from_dict(key: str, raw: dict[str, Any]) -> SAMLProvider:
    return SAMLProvider(
        key=key,
        display_name=raw.get("display_name") or key,
        idp_entity_id=raw.get("idp_entity_id") or "",
        idp_sso_url=raw.get("idp_sso_url") or "",
        idp_x509_cert=raw.get("idp_x509_cert") or "",
        sp_entity_id=raw.get("sp_entity_id") or "",
        acs_url=raw.get("acs_url") or "",
        group_attribute=raw.get("group_attribute") or "groups",
        email_attribute=raw.get("email_attribute") or "email",
        name_attribute=raw.get("name_attribute") or "name",
        subject_attribute=raw.get("subject_attribute") or "nameID",
        allow_auto_create=bool(raw.get("allow_auto_create", False)),
        enabled=bool(raw.get("enabled", True)),
    )


def _oidc_provider_from_env(key: str) -> OIDCProvider:
    return _oidc_provider_from_dict(
        key,
        {
            "display_name": settings.oidc_display_name,
            "issuer": settings.oidc_issuer,
            "client_id": settings.oidc_client_id,
            "client_secret": settings.oidc_client_secret,
            "authorization_endpoint": settings.oidc_authorization_endpoint,
            "token_endpoint": settings.oidc_token_endpoint,
            "jwks_uri": settings.oidc_jwks_uri,
            "scopes": settings.oidc_scopes,
            "group_claim": settings.oidc_group_claim,
            "email_claim": settings.oidc_email_claim,
            "name_claim": settings.oidc_name_claim,
            "subject_claim": settings.oidc_subject_claim,
            "allow_auto_create": settings.oidc_allow_auto_create,
            "enabled": settings.oidc_enabled,
        },
    )


def _saml_provider_from_env(key: str) -> SAMLProvider:
    return _saml_provider_from_dict(
        key,
        {
            "display_name": settings.saml_display_name,
            "idp_entity_id": settings.saml_idp_entity_id,
            "idp_sso_url": settings.saml_idp_sso_url,
            "idp_x509_cert": settings.saml_idp_x509_cert,
            "sp_entity_id": settings.saml_sp_entity_id,
            "acs_url": settings.saml_acs_url,
            "group_attribute": settings.saml_group_attribute,
            "email_attribute": settings.saml_email_attribute,
            "name_attribute": settings.saml_name_attribute,
            "subject_attribute": settings.saml_subject_attribute,
            "allow_auto_create": settings.saml_allow_auto_create,
            "enabled": settings.saml_enabled,
        },
    )


def get_runtime_sso_config() -> SSORuntimeConfig:
    oidc_providers: dict[str, dict[str, Any]] = {}
    saml_providers: dict[str, dict[str, Any]] = {}
    if settings.oidc_enabled:
        oidc_providers[settings.oidc_key] = {
            "display_name": settings.oidc_display_name,
            "issuer": settings.oidc_issuer,
            "client_id": settings.oidc_client_id,
            "client_secret": settings.oidc_client_secret,
            "authorization_endpoint": settings.oidc_authorization_endpoint,
            "token_endpoint": settings.oidc_token_endpoint,
            "jwks_uri": settings.oidc_jwks_uri,
            "scopes": settings.oidc_scopes,
            "group_claim": settings.oidc_group_claim,
            "email_claim": settings.oidc_email_claim,
            "name_claim": settings.oidc_name_claim,
            "subject_claim": settings.oidc_subject_claim,
            "allow_auto_create": settings.oidc_allow_auto_create,
            "enabled": settings.oidc_enabled,
        }
    if settings.saml_enabled:
        saml_providers[settings.saml_key] = {
            "display_name": settings.saml_display_name,
            "idp_entity_id": settings.saml_idp_entity_id,
            "idp_sso_url": settings.saml_idp_sso_url,
            "idp_x509_cert": settings.saml_idp_x509_cert,
            "sp_entity_id": settings.saml_sp_entity_id,
            "acs_url": settings.saml_acs_url,
            "group_attribute": settings.saml_group_attribute,
            "email_attribute": settings.saml_email_attribute,
            "name_attribute": settings.saml_name_attribute,
            "subject_attribute": settings.saml_subject_attribute,
            "allow_auto_create": settings.saml_allow_auto_create,
            "enabled": settings.saml_enabled,
        }
    return SSORuntimeConfig(
        enabled=bool(settings.sso_enabled or settings.oidc_enabled or settings.saml_enabled),
        auto_create_users=bool(settings.sso_auto_create_users),
        sync_roles_on_login=bool(settings.sso_sync_roles_on_login),
        default_role=str(settings.sso_default_role or "viewer").lower(),
        group_role_map=settings.sso_group_role_map_dict,
        oidc_providers=oidc_providers,
        saml_providers=saml_providers,
    )


async def load_sso_config(db: AsyncSession) -> SSORuntimeConfig:
    """Load SSO configuration, preferring the DB-backed AppSetting override and
    falling back to environment-derived defaults when no override exists."""
    env_cfg = get_runtime_sso_config()
    result = await db.execute(select(AppSetting).where(AppSetting.key == "sso_config"))
    row = result.scalar_one_or_none()
    if row is None:
        return env_cfg
    try:
        data = json.loads(row.value)
    except Exception:
        return env_cfg
    if not isinstance(data, dict):
        return env_cfg
    oidc_list = [p for p in data.get("oidc_providers", []) if isinstance(p, dict)]
    saml_list = [p for p in data.get("saml_providers", []) if isinstance(p, dict)]
    return SSORuntimeConfig(
        enabled=bool(data.get("enabled", env_cfg.enabled)),
        auto_create_users=bool(data.get("auto_create_users", env_cfg.auto_create_users)),
        sync_roles_on_login=bool(data.get("sync_roles_on_login", env_cfg.sync_roles_on_login)),
        default_role=str(data.get("default_role", env_cfg.default_role)).lower(),
        group_role_map=data.get("group_role_map") or {},
        oidc_providers={p["key"]: p for p in oidc_list if p.get("key")},
        saml_providers={p["key"]: p for p in saml_list if p.get("key")},
    )


def get_oidc_provider(provider: str, config: SSORuntimeConfig) -> OIDCProvider:
    raw = (config.oidc_providers or {}).get(provider)
    if not raw:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="OIDC provider not configured"
        )
    parsed = _oidc_provider_from_dict(provider, raw)
    if not parsed.enabled:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="OIDC provider disabled")
    return parsed


def get_saml_provider(provider: str, config: SSORuntimeConfig) -> SAMLProvider:
    raw = (config.saml_providers or {}).get(provider)
    if not raw:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="SAML provider not configured"
        )
    parsed = _saml_provider_from_dict(provider, raw)
    if not parsed.enabled:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="SAML provider disabled")
    return parsed


def list_enabled_providers(config: SSORuntimeConfig) -> list[SSOProviderSummary]:
    out: list[SSOProviderSummary] = []
    for key, raw in (config.oidc_providers or {}).items():
        provider = _oidc_provider_from_dict(key, raw)
        if not provider.enabled:
            continue
        out.append(
            SSOProviderSummary(
                provider=provider.key,
                kind="oidc",  # type: ignore[arg-type]
                display_name=provider.display_name,
                enabled=provider.enabled,
                auto_create_users=provider.allow_auto_create,
            )
        )
    for key, raw in (config.saml_providers or {}).items():
        provider = _saml_provider_from_dict(key, raw)
        if not provider.enabled:
            continue
        out.append(
            SSOProviderSummary(
                provider=provider.key,
                kind="saml",  # type: ignore[arg-type]
                display_name=provider.display_name,
                enabled=provider.enabled,
                auto_create_users=provider.allow_auto_create,
            )
        )
    return out


def _sign_state(token: str, timestamp: int) -> str:
    message = f"{token}:{timestamp}".encode()
    key = settings.jwt_secret_key.encode("utf-8")
    return hmac.new(key, message, hashlib.sha256).hexdigest()


def build_oidc_authorize_url(provider: OIDCProvider, redirect_uri: str) -> tuple[str, str]:
    token = secrets.token_urlsafe(16)
    timestamp = int(datetime.now(UTC).timestamp())
    signature = _sign_state(token, timestamp)
    state_payload = f"{token}:{timestamp}:{signature}"
    state = base64.urlsafe_b64encode(state_payload.encode()).decode().rstrip("=")
    params = {
        "client_id": provider.client_id,
        "response_type": "code",
        "scope": provider.scopes,
        "redirect_uri": redirect_uri,
        "state": state,
        "nonce": secrets.token_urlsafe(16),
    }
    from urllib.parse import urlencode

    return f"{provider.authorization_endpoint}?{urlencode(params)}", state


def verify_oidc_state(provided_state: str | None, expected_state: str | None) -> bool:
    if not provided_state:
        return False
    try:
        if expected_state is not None and not hmac.compare_digest(provided_state, expected_state):
            return False
        missing_padding = (-len(provided_state)) % 4
        padded = provided_state + ("=" * missing_padding)
        decoded = base64.urlsafe_b64decode(padded).decode("utf-8")
        parts = decoded.split(":")
        if len(parts) != 3:
            return False
        token, timestamp_str, provided_signature = parts
        timestamp = int(timestamp_str)
        now = int(datetime.now(UTC).timestamp())
        if now - timestamp > _OIDC_STATE_EXPIRY_SECONDS:
            return False
        expected_signature = _sign_state(token, timestamp)
        return hmac.compare_digest(provided_signature, expected_signature)
    except Exception:
        return False


async def exchange_oidc_code(
    provider: OIDCProvider, code: str, redirect_uri: str
) -> dict[str, Any]:
    token_payload = {
        "grant_type": "authorization_code",
        "client_id": provider.client_id,
        "client_secret": provider.client_secret,
        "code": code,
        "redirect_uri": redirect_uri,
    }
    async with httpx.AsyncClient(timeout=15.0) as client:
        resp = await client.post(
            provider.token_endpoint,
            data=token_payload,
            headers={"Accept": "application/json"},
        )
        resp.raise_for_status()
        token_data = resp.json()
        jwks_resp = await client.get(provider.jwks_uri, headers={"Accept": "application/json"})
        jwks_resp.raise_for_status()
        jwks = jwks_resp.json()

    id_token = str(token_data.get("id_token") or "").strip()
    if not id_token:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Missing id_token in OIDC token response",
        )

    keys = jwks.get("keys") if isinstance(jwks.get("keys"), list) else []
    if not keys:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="OIDC JWKS fetch failed"
        )

    decode_kwargs: dict[str, Any] = {
        "algorithms": ["RS256", "RS384", "RS512", "ES256", "ES384", "ES512"],
        "audience": provider.client_id,
    }
    if provider.issuer:
        decode_kwargs["issuer"] = provider.issuer

    claims: dict[str, Any] | None = None
    last_err: Exception | None = None
    for key in keys:
        try:
            key_obj = _jwk_to_key(key)
        except Exception as err:
            last_err = err
            continue
        try:
            claims = jwt.decode(id_token, key_obj, **decode_kwargs)
            break
        except Exception as err:
            last_err = err
            continue

    if claims is None:
        detail = f"Invalid OIDC token: {last_err}" if last_err else "Invalid OIDC token"
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail=detail)
    return claims


def _jwk_to_key(jwk: dict[str, Any]):
    kty = str(jwk.get("kty") or "").upper()
    if kty == "RSA":
        return RSAAlgorithm.from_jwk(jwk)
    if kty == "EC":
        return ECAlgorithm.from_jwk(jwk)
    if kty in ("OKP", "ED25519", "ED448", "X25519", "X448"):
        from jwt.algorithms import OKPAlgorithm

        return OKPAlgorithm.from_jwk(jwk)
    raise ValueError(f"Unsupported JWK type: {kty}")


def resolve_role_from_groups(groups: list[str], runtime: SSORuntimeConfig) -> str:
    mapping = runtime.group_role_map
    if not mapping:
        return runtime.default_role
    best_role = runtime.default_role
    best_score = _ROLE_PRIORITY.get(best_role, 0)
    lower_map = {k.lower(): v.lower() for k, v in mapping.items()}
    for raw in groups:
        role = lower_map.get(str(raw).strip().lower())
        if not role or role not in VALID_ROLES:
            continue
        score = _ROLE_PRIORITY.get(role, 0)
        if score > best_score:
            best_score = score
            best_role = role
    return best_role


def _normalize_groups(groups: Any) -> list[str]:
    if groups is None:
        return []
    if isinstance(groups, str):
        return [groups]
    if isinstance(groups, list):
        return [str(v) for v in groups if v is not None]
    return []


def claims_to_identity(provider: OIDCProvider, claims: dict[str, Any]) -> dict[str, Any]:
    subject = str(claims.get(provider.subject_claim) or "").strip()
    email = str(claims.get(provider.email_claim) or claims.get("email") or "").strip()
    full_name = str(claims.get(provider.name_claim) or claims.get("name") or email).strip()
    groups = _normalize_groups(claims.get(provider.group_claim))
    if not subject:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail="Missing OIDC subject claim"
        )
    if not email:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail="Missing OIDC email claim"
        )
    return {"subject": subject, "email": email, "full_name": full_name, "groups": groups}


def parse_saml_response(provider: SAMLProvider, saml_response: str) -> dict[str, Any]:
    try:
        from onelogin.saml2.auth import OneLogin_Saml2_Auth
    except Exception as exc:  # pragma: no cover
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="SAML support requires python3-saml package",
        ) from exc

    request_data = {
        "https": "on",
        "http_host": "localhost",
        "server_port": "443",
        "script_name": provider.acs_url,
        "get_data": {},
        "post_data": {"SAMLResponse": saml_response},
    }
    saml_settings = {
        "strict": True,
        "debug": False,
        "sp": {
            "entityId": provider.sp_entity_id,
            "assertionConsumerService": {
                "url": provider.acs_url,
                "binding": "urn:oasis:names:tc:SAML:2.0:bindings:HTTP-POST",
            },
        },
        "idp": {
            "entityId": provider.idp_entity_id,
            "singleSignOnService": {
                "url": provider.idp_sso_url,
                "binding": "urn:oasis:names:tc:SAML:2.0:bindings:HTTP-Redirect",
            },
            "x509cert": provider.idp_x509_cert,
        },
    }

    auth = OneLogin_Saml2_Auth(request_data, old_settings=saml_settings)
    auth.process_response()
    errors = auth.get_errors()
    if errors:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=f"Invalid SAML response: {','.join(errors)}",
        )
    if not auth.is_authenticated():
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail="SAML authentication failed"
        )

    attrs = auth.get_attributes() or {}
    subject = auth.get_nameid() or _first(attrs.get(provider.subject_attribute))
    email = _first(attrs.get(provider.email_attribute), fallback=subject)
    full_name = _first(attrs.get(provider.name_attribute), fallback=email)
    groups = _normalize_groups(attrs.get(provider.group_attribute))
    if not subject:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Missing SAML subject")
    if not email:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Missing SAML email")
    return {"subject": subject, "email": email, "full_name": full_name, "groups": groups}


def _first(values: Any, fallback: str = "") -> str:
    if isinstance(values, list):
        if not values:
            return fallback
        return str(values[0] or fallback)
    if values is None:
        return fallback
    return str(values)


async def upsert_external_user(
    db: AsyncSession,
    *,
    provider_key: str,
    source: str,
    subject: str,
    email: str,
    full_name: str,
    groups: list[str],
    allow_auto_create: bool,
    runtime: SSORuntimeConfig,
) -> User:

    desired_role = resolve_role_from_groups(groups, runtime)
    existing = await _find_existing_user(db, provider_key, subject, email)
    if existing is None and not allow_auto_create:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="SSO account is not provisioned and auto-create is disabled",
        )

    name_parts = (full_name or email).strip().split(None, 1)
    first_name = name_parts[0] if name_parts else ""
    last_name = name_parts[1] if len(name_parts) > 1 else ""

    if existing is None:
        existing = User(
            email=email,
            password_hash=hash_password(secrets.token_urlsafe(48)),
            first_name=first_name,
            last_name=last_name,
            full_name=full_name or email,
            role=desired_role,
            is_active=True,
            is_admin=desired_role == "admin",
            auth_source=source,
            external_provider=provider_key,
            external_subject=subject,
        )
        db.add(existing)
    else:
        existing.auth_source = source
        existing.external_provider = provider_key
        existing.external_subject = subject
        if full_name and full_name != existing.full_name:
            existing.first_name = first_name
            existing.last_name = last_name
            existing.full_name = full_name

    if runtime.sync_roles_on_login and desired_role in VALID_ROLES:
        existing.role = desired_role
        existing.is_admin = desired_role == "admin"

    await db.commit()
    await db.refresh(existing)

    if not existing.is_active:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Account disabled")
    await _ensure_mapped_role_exists(db, existing, desired_role)
    return existing


async def _find_existing_user(
    db: AsyncSession, provider_key: str, subject: str, email: str
) -> User | None:
    if provider_key and subject:
        result = await db.execute(
            select(User).where(
                User.external_provider == provider_key,
                User.external_subject == subject,
            )
        )
        existing = result.scalar_one_or_none()
        if existing is not None:
            return existing
    if email:
        result = await db.execute(select(User).where(func.lower(User.email) == email.lower()))
        return result.scalar_one_or_none()
    return None


async def _ensure_mapped_role_exists(db: AsyncSession, user: User, role_name: str) -> None:
    if role_name not in VALID_ROLES:
        return
    result = await db.execute(select(Role).where(Role.name == role_name))
    role = result.scalar_one_or_none()
    if role is None:
        return
    if any(r.id == role.id for r in user.roles):
        return
    user.roles.append(role)
    db.add(user)
    await db.commit()
    await db.refresh(user)


def build_saml_redirect_url(saml: SAMLProvider) -> str:
    api_base = settings.public_api_base_url
    parsed = urlparse(api_base)
    request_data = {
        "https": "on" if parsed.scheme == "https" else "off",
        "http_host": parsed.netloc,
        "script_name": "/api/v1/auth/sso/saml/acs",
        "get_data": {},
        "post_data": {},
    }
    auth = OneLogin_Saml2_Auth(request_data, saml.to_settings())
    return auth.login()
