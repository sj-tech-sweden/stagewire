import base64
import json
import logging
from datetime import UTC, datetime, timedelta
from typing import Any
from urllib.parse import urlparse

from fastapi import APIRouter, Depends, Form, HTTPException, Request, Response, status
from fastapi.responses import RedirectResponse
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.core.db import get_db
from app.domains.auth.deps import get_current_user, require_admin
from app.domains.auth.models import APIKey, AppSetting, Role, User, UserRole, UserSession
from app.domains.auth.schemas import (
    APIKeyCreate,
    APIKeyOut,
    ForgotPasswordRequest,
    OIDCExchangeRequest,
    OIDCProviderConfig,
    ResetPasswordRequest,
    RoleAssign,
    RoleCreate,
    SAMLAssertionRequest,
    SAMLProviderConfig,
    SSOConfig,
    SSOProviderSummary,
    Token,
    UserCreate,
    UserLogin,
    UserSelfUpdate,
    UserSummary,
    UserUpdate,
)
from app.domains.auth.security import (
    compute_refresh_token_hash,
    create_access_token,
    decode_token,
    generate_refresh_token,
    hash_api_key,
    hash_api_key_lookup,
    hash_password,
    verify_password,
)
from app.domains.auth.sso import (
    build_oidc_authorize_url,
    build_saml_redirect_url,
    claims_to_identity,
    exchange_oidc_code,
    get_oidc_provider,
    get_saml_provider,
    list_enabled_providers,
    load_sso_config,
    parse_saml_response,
    upsert_external_user,
    verify_oidc_state,
)

settings = get_settings()
logger = logging.getLogger(__name__)

router = APIRouter(prefix="/auth", tags=["auth"])


def _set_refresh_cookie(response: Response, refresh_token: str) -> None:
    max_age = settings.jwt_refresh_expire_days * 24 * 60 * 60
    response.set_cookie(
        key="refresh_token",
        value=refresh_token,
        httponly=True,
        samesite="none",
        secure=settings.secure_cookies,
        path="/api/v1/auth",
        max_age=max_age,
    )


def _clear_refresh_cookie(response: Response) -> None:
    response.set_cookie(
        key="refresh_token",
        value="",
        httponly=True,
        samesite="none",
        secure=settings.secure_cookies,
        path="/api/v1/auth",
        max_age=0,
    )


def _create_refresh_session(db: AsyncSession, user: User) -> str:
    refresh_token = generate_refresh_token()
    token_hash = compute_refresh_token_hash(refresh_token)
    expires_at = datetime.now(UTC) + timedelta(days=settings.jwt_refresh_expire_days)
    session = UserSession(session_id=token_hash, user_id=user.id, expires_at=expires_at)
    db.add(session)
    return refresh_token


async def _make_token_response(user: User, response: Response, db: AsyncSession) -> Token:
    access_token_str = create_access_token(user.id, user.email, user.role)
    refresh_token = _create_refresh_session(db, user)
    await db.commit()
    _set_refresh_cookie(response, refresh_token)
    token = Token(
        access_token=access_token_str,
        user=UserSummary.model_validate(user),
        refresh_token=refresh_token,
    )
    return token


def _decode_saml_relay_state(relay_state: str) -> dict[str, Any]:
    if not relay_state:
        return {}
    try:
        decoded = base64.urlsafe_b64decode(relay_state.encode()).decode("utf-8")
        parsed = json.loads(decoded)
        return parsed if isinstance(parsed, dict) else {}
    except Exception:
        return {}


def _saml_error_redirect(detail: str) -> RedirectResponse:
    encoded = base64.urlsafe_b64encode(detail.encode("utf-8")).decode().rstrip("=")
    target = f"{settings.effective_frontend_base_url}/login?reason=saml_error&detail={encoded}"
    return RedirectResponse(url=target, status_code=status.HTTP_303_SEE_OTHER)


def _decode_saml_redirect(relay_state: str) -> str | None:
    redirect = _decode_saml_relay_state(relay_state).get("redirect")
    if not isinstance(redirect, str):
        return None
    candidate = redirect.replace("\\", "/")
    parsed = urlparse(candidate)
    if (
        candidate.startswith("/")
        and not candidate.startswith("//")
        and not parsed.scheme
        and not parsed.netloc
    ):
        return candidate
    return None


@router.get("/sso/providers", response_model=list[SSOProviderSummary])
async def sso_providers(db: AsyncSession = Depends(get_db)) -> list[SSOProviderSummary]:
    config = await load_sso_config(db)
    if not config.enabled:
        return []
    return list_enabled_providers(config)


@router.get("/sso/config", response_model=SSOConfig)
async def get_sso_config(
    db: AsyncSession = Depends(get_db), _: User = Depends(require_admin)
) -> SSOConfig:
    config = await load_sso_config(db)
    return SSOConfig(
        enabled=config.enabled,
        auto_create_users=config.auto_create_users,
        sync_roles_on_login=config.sync_roles_on_login,
        default_role=config.default_role,
        group_role_map=config.group_role_map,
        oidc_providers=[OIDCProviderConfig(**v) for v in config.oidc_providers.values()],
        saml_providers=[SAMLProviderConfig(**v) for v in config.saml_providers.values()],
    )


@router.put("/sso/config", response_model=SSOConfig)
async def update_sso_config(
    payload: SSOConfig,
    db: AsyncSession = Depends(get_db),
    _: User = Depends(require_admin),
) -> SSOConfig:
    data = payload.model_dump(mode="json")
    result = await db.execute(select(AppSetting).where(AppSetting.key == "sso_config"))
    row = result.scalar_one_or_none()
    now = datetime.now(UTC)
    if row is None:
        row = AppSetting(key="sso_config", value=json.dumps(data), updated_at=now)
        db.add(row)
    else:
        row.value = json.dumps(data)
        row.updated_at = now
    await db.commit()
    await db.refresh(row)
    return payload


@router.get("/sso/oidc/authorize/{provider}")
async def oidc_authorize(
    provider: str, redirect_uri: str, response: Response, db: AsyncSession = Depends(get_db)
) -> dict:
    config = await load_sso_config(db)
    if not config.enabled:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="SSO not enabled")
    oidc = get_oidc_provider(provider, config)
    if not redirect_uri:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail="redirect_uri is required"
        )
    authorize_url, state = build_oidc_authorize_url(oidc, redirect_uri)
    response.set_cookie(
        key="oidc_state",
        value=state,
        httponly=True,
        secure=settings.secure_cookies,
        samesite="lax",
        path="/api/v1/auth",
        max_age=600,
    )
    return RedirectResponse(url=authorize_url, status_code=status.HTTP_303_SEE_OTHER)


@router.get("/sso/saml/redirect/{provider}")
async def saml_redirect(provider: str, db: AsyncSession = Depends(get_db)) -> RedirectResponse:
    config = await load_sso_config(db)
    if not config.enabled:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="SSO not enabled")
    saml = get_saml_provider(provider, config)
    url = build_saml_redirect_url(saml)
    return RedirectResponse(url=url, status_code=status.HTTP_303_SEE_OTHER)


@router.post("/sso/oidc/exchange", response_model=Token)
async def oidc_exchange(
    payload: OIDCExchangeRequest,
    request: Request,
    response: Response,
    db: AsyncSession = Depends(get_db),
) -> Token:
    config = await load_sso_config(db)
    if not config.enabled:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="SSO not enabled")
    expected_state = request.cookies.get("oidc_state")
    if not verify_oidc_state(payload.state, expected_state):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN, detail="Invalid or expired OIDC state"
        )
    response.delete_cookie("oidc_state", path="/api/v1/auth")
    oidc = get_oidc_provider(payload.provider, config)
    claims = await exchange_oidc_code(oidc, payload.code, payload.redirect_uri)
    identity = claims_to_identity(oidc, claims)
    user = await upsert_external_user(
        db,
        provider_key=oidc.key,
        source="oidc",
        subject=identity["subject"],
        email=identity["email"],
        full_name=identity["full_name"],
        groups=identity["groups"],
        allow_auto_create=oidc.allow_auto_create,
        runtime=config,
    )
    return await _make_token_response(user, response, db)


@router.post("/sso/saml/login", response_model=Token)
async def saml_login(
    payload: SAMLAssertionRequest,
    response: Response,
    db: AsyncSession = Depends(get_db),
) -> Token:
    config = await load_sso_config(db)
    if not config.enabled:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="SSO not enabled")
    saml = get_saml_provider(payload.provider, config)
    identity = parse_saml_response(saml, payload.saml_response)
    user = await upsert_external_user(
        db,
        provider_key=saml.key,
        source="saml",
        subject=identity["subject"],
        email=identity["email"],
        full_name=identity["full_name"],
        groups=identity["groups"],
        allow_auto_create=saml.allow_auto_create,
        runtime=config,
    )
    return await _make_token_response(user, response, db)


@router.post("/sso/saml/acs")
async def saml_acs(
    response: Response,
    db: AsyncSession = Depends(get_db),
    saml_response: str = Form(..., alias="SAMLResponse"),
    relay_state: str = Form(default="", alias="RelayState"),
) -> Response:
    config = await load_sso_config(db)
    if not config.enabled:
        return _saml_error_redirect("SSO not enabled")
    provider_key = _decode_saml_relay_state(relay_state).get("provider")
    if not provider_key:
        return _saml_error_redirect("Invalid SAML relay state")
    try:
        saml = get_saml_provider(provider_key, config)
    except HTTPException as exc:
        return _saml_error_redirect(str(exc.detail))
    try:
        identity = parse_saml_response(saml, saml_response)
        user = await upsert_external_user(
            db,
            provider_key=saml.key,
            source="saml",
            subject=identity["subject"],
            email=identity["email"],
            full_name=identity["full_name"],
            groups=identity["groups"],
            allow_auto_create=saml.allow_auto_create,
            runtime=config,
        )
    except HTTPException as exc:
        return _saml_error_redirect(str(exc.detail))
    access_token_str = create_access_token(user.id, user.email, user.role)
    refresh_token = _create_refresh_session(db, user)
    await db.commit()
    _set_refresh_cookie(response, refresh_token)
    redirect_path = _decode_saml_redirect(relay_state) or "/"
    fragment = f"access_token={access_token_str}&refresh_token={refresh_token}"
    target = f"{settings.effective_frontend_base_url}{redirect_path}#{fragment}"
    return RedirectResponse(url=target, status_code=status.HTTP_303_SEE_OTHER)


@router.get("/bootstrap-status")
async def bootstrap_status(db: AsyncSession = Depends(get_db)) -> dict:
    result = await db.execute(select(func.count()).select_from(User))
    count = result.scalar() or 0
    return {"setup_needed": count == 0}


@router.post("/setup", response_model=Token, status_code=status.HTTP_201_CREATED)
async def setup_admin(
    payload: UserCreate, response: Response, db: AsyncSession = Depends(get_db)
) -> Token:
    result = await db.execute(select(func.count()).select_from(User))
    count = result.scalar() or 0
    if count and count > 0:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Setup already complete")
    user = User(
        email=payload.email.strip().lower(),
        password_hash=hash_password(payload.password),
        first_name=payload.first_name.strip(),
        last_name=payload.last_name.strip(),
        full_name=payload.full_name or f"{payload.first_name} {payload.last_name}".strip(),
        role="admin",
        is_active=True,
        is_admin=True,
        auth_source="local",
    )
    try:
        db.add(user)
        await db.commit()
        await db.refresh(user)
    except IntegrityError:
        # Concurrent first-time setup: another request already created the
        # initial admin. Roll back and authenticate against the existing user.
        await db.rollback()
        existing = (
            await db.execute(select(User).where(User.email == user.email))
        ).scalar_one_or_none()
        if existing is None:
            raise
        user = existing
    return await _make_token_response(user, response, db)


@router.post("/login", response_model=Token)
async def login(
    payload: UserLogin, response: Response, db: AsyncSession = Depends(get_db)
) -> Token:
    identifier = str(payload.email or "").strip().lower()
    result = await db.execute(select(User).where(func.lower(User.email) == identifier))
    user = result.scalar_one_or_none()
    if user is None:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid credentials")
    if not verify_password(payload.password, user.password_hash or ""):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid credentials")
    if not user.is_active:
        raise HTTPException(status_code=status.HTTP_403_FORBANNED, detail="Account disabled")
    return await _make_token_response(user, response, db)


@router.post("/forgot-password", status_code=status.HTTP_204_NO_CONTENT)
async def forgot_password(
    payload: ForgotPasswordRequest, db: AsyncSession = Depends(get_db)
) -> None:
    normalized = payload.email.strip().lower()
    result = await db.execute(select(User).where(func.lower(User.email) == normalized))
    if result.scalar_one_or_none() is None:
        return
    # Email sending is out of scope for the first pass; log intent.
    logger.info("Password reset requested for %s (email send not configured)", normalized)


@router.post("/reset-password", status_code=status.HTTP_204_NO_CONTENT)
async def reset_password(payload: ResetPasswordRequest, db: AsyncSession = Depends(get_db)) -> None:
    try:
        claims = decode_token(payload.token)
    except Exception as err:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid or expired token"
        ) from err
    if claims.get("purpose") != "password_reset":
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid token purpose")
    user = await db.get(User, int(claims["sub"]))
    if user is None:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid or expired token"
        )
    user.password_hash = hash_password(payload.new_password)
    db.add(user)
    await db.commit()


@router.post("/refresh", response_model=Token)
async def refresh_token(
    response: Response, request: Request, db: AsyncSession = Depends(get_db)
) -> Token:
    refresh_token = request.headers.get("X-Refresh-Token") or request.cookies.get("refresh_token")
    if not refresh_token:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail="Refresh token missing"
        )
    token_hash = compute_refresh_token_hash(refresh_token)
    session = await db.get(UserSession, token_hash)
    if session is None:
        _clear_refresh_cookie(response)
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid refresh token"
        )
    now = datetime.now(UTC)
    expires_at = session.expires_at
    if expires_at.tzinfo is None:
        expires_at = expires_at.replace(tzinfo=UTC)
    if expires_at < now:
        await db.delete(session)
        await db.commit()
        _clear_refresh_cookie(response)
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail="Refresh token expired"
        )
    user = await db.get(User, session.user_id)
    if user is None or not user.is_active:
        await db.delete(session)
        await db.commit()
        _clear_refresh_cookie(response)
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail="User not found or inactive"
        )
    session.expires_at = datetime.now(UTC) + timedelta(
        seconds=settings.jwt_refresh_reuse_grace_seconds
    )
    db.add(session)
    await db.commit()
    new_token = create_access_token(user.id, user.email, user.role)
    new_refresh = _create_refresh_session(db, user)
    await db.commit()
    _set_refresh_cookie(response, new_refresh)
    result = Token(
        access_token=new_token, user=UserSummary.model_validate(user), refresh_token=new_refresh
    )
    return result


@router.post("/logout", status_code=status.HTTP_204_NO_CONTENT)
async def logout(
    response: Response, request: Request, db: AsyncSession = Depends(get_db)
) -> Response:
    refresh_token = request.cookies.get("refresh_token") or request.headers.get("X-Refresh-Token")
    if refresh_token:
        token_hash = compute_refresh_token_hash(refresh_token)
        session = await db.get(UserSession, token_hash)
        if session is not None:
            await db.delete(session)
            await db.commit()
    _clear_refresh_cookie(response)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.get("/me", response_model=UserSummary)
async def me(current_user: User = Depends(get_current_user)) -> User:
    return current_user


@router.put("/me", response_model=UserSummary)
async def update_me(
    payload: UserSelfUpdate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> User:
    if str(current_user.auth_source or "local").strip().lower() in {"oidc", "saml"}:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN, detail="Profile managed by your SSO provider"
        )
    normalized_email = str(payload.email or "").strip().lower()
    if not normalized_email:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Email is required")
    result = await db.execute(select(User).where(func.lower(User.email) == normalized_email))
    existing = result.scalar_one_or_none()
    if existing and existing.id != current_user.id:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Email already registered")
    current_user.email = normalized_email
    current_user.first_name = str(payload.first_name or "").strip() or current_user.first_name
    current_user.last_name = str(payload.last_name or "").strip() or current_user.last_name
    current_user.full_name = (
        payload.full_name or f"{current_user.first_name} {current_user.last_name}".strip()
    )
    new_password = str(payload.password or "").strip()
    if new_password:
        current_user.password_hash = hash_password(new_password)
    db.add(current_user)
    await db.commit()
    await db.refresh(current_user)
    return current_user


@router.get("/users", response_model=list[UserSummary])
async def list_users(
    db: AsyncSession = Depends(get_db), _: User = Depends(get_current_user)
) -> list[User]:
    result = await db.execute(select(User).order_by(User.id))
    return [UserSummary.model_validate(u) for u in result.scalars().all()]


@router.post("/users", response_model=UserSummary, status_code=status.HTTP_201_CREATED)
async def create_user(
    payload: UserCreate, db: AsyncSession = Depends(get_db), _: User = Depends(require_admin)
) -> User:
    normalized_email = str(payload.email or "").strip().lower()
    if not normalized_email:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Email is required")
    result = await db.execute(select(User).where(func.lower(User.email) == normalized_email))
    if result.scalar_one_or_none():
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Email already registered")
    user = User(
        email=normalized_email,
        password_hash=hash_password(payload.password),
        first_name=payload.first_name.strip(),
        last_name=payload.last_name.strip(),
        full_name=payload.full_name or f"{payload.first_name} {payload.last_name}".strip(),
        role=payload.role,
        is_active=payload.is_active,
        is_admin=payload.role == "admin",
        auth_source="local",
    )
    db.add(user)
    await db.commit()
    await db.refresh(user)
    return user


@router.get("/users/{user_id}", response_model=UserSummary)
async def get_user(
    user_id: int, db: AsyncSession = Depends(get_db), _: User = Depends(get_current_user)
) -> User:
    user = await db.get(User, user_id)
    if user is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")
    return user


@router.put("/users/{user_id}", response_model=UserSummary)
async def update_user(
    user_id: int,
    payload: UserUpdate,
    db: AsyncSession = Depends(get_db),
    _: User = Depends(require_admin),
) -> User:
    user = await db.get(User, user_id)
    if user is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")
    if payload.email is not None:
        normalized = str(payload.email).strip().lower()
        if not normalized:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Email is required")
        result = await db.execute(
            select(User).where(func.lower(User.email) == normalized, User.id != user_id)
        )
        if result.scalar_one_or_none():
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT, detail="Email already registered"
            )
        user.email = normalized
    if payload.password is not None and payload.password:
        user.password_hash = hash_password(payload.password)
    if payload.first_name is not None:
        user.first_name = payload.first_name.strip()
    if payload.last_name is not None:
        user.last_name = payload.last_name.strip()
    if payload.full_name is not None:
        user.full_name = payload.full_name
    if payload.role is not None:
        user.role = payload.role
        user.is_admin = payload.role == "admin"
    if payload.is_active is not None:
        user.is_active = payload.is_active
    if payload.preferred_language is not None:
        user.preferred_language = str(payload.preferred_language).strip().lower() or "en"
    db.add(user)
    await db.commit()
    await db.refresh(user)
    return user


@router.delete("/users/{user_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_user(
    user_id: int, db: AsyncSession = Depends(get_db), _: User = Depends(require_admin)
) -> None:
    user = await db.get(User, user_id)
    if user is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")
    await db.delete(user)
    await db.commit()


@router.get("/roles")
async def list_roles(db: AsyncSession = Depends(get_db), _: User = Depends(get_current_user)):
    result = await db.execute(select(Role).order_by(Role.id))
    return [
        {"id": r.id, "name": r.name, "display_name": r.display_name, "permissions": r.permissions}
        for r in result.scalars().all()
    ]


@router.post("/roles", status_code=status.HTTP_201_CREATED)
async def create_role(
    payload: RoleCreate, db: AsyncSession = Depends(get_db), _: User = Depends(require_admin)
):
    role = Role(
        name=payload.name,
        display_name=payload.display_name,
        permissions=json.dumps(payload.permissions or []),
    )
    db.add(role)
    await db.commit()
    await db.refresh(role)
    return {
        "id": role.id,
        "name": role.name,
        "display_name": role.display_name,
        "permissions": role.permissions,
    }


@router.get("/users/{user_id}/roles")
async def list_user_roles(
    user_id: int, db: AsyncSession = Depends(get_db), _: User = Depends(get_current_user)
):
    user = await db.get(User, user_id)
    if user is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")
    return [{"id": r.id, "name": r.name} for r in user.roles]


@router.post("/users/{user_id}/roles", status_code=status.HTTP_201_CREATED)
async def assign_role_to_user(
    user_id: int,
    payload: RoleAssign,
    db: AsyncSession = Depends(get_db),
    _: User = Depends(require_admin),
):
    user = await db.get(User, user_id)
    if user is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")
    role = await db.get(Role, payload.role_id)
    if role is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Role not found")
    result = await db.execute(
        select(UserRole).where(UserRole.user_id == user_id, UserRole.role_id == role.id)
    )
    if result.scalar_one_or_none():
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="User already has role")
    ur = UserRole(user_id=user_id, role_id=role.id, is_active=True)
    db.add(ur)
    await db.commit()
    return {"id": role.id, "name": role.name}


@router.delete("/users/{user_id}/roles/{role_id}", status_code=status.HTTP_204_NO_CONTENT)
async def remove_role_from_user(
    user_id: int, role_id: int, db: AsyncSession = Depends(get_db), _: User = Depends(require_admin)
) -> None:
    result = await db.execute(
        select(UserRole).where(UserRole.user_id == user_id, UserRole.role_id == role_id)
    )
    ur = result.scalar_one_or_none()
    if ur is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Role assignment not found"
        )
    await db.delete(ur)
    await db.commit()


@router.get("/api-keys", response_model=list[APIKeyOut])
async def list_api_keys(db: AsyncSession = Depends(get_db), _: User = Depends(require_admin)):
    result = await db.execute(select(APIKey).where(APIKey.is_active.is_(True)).order_by(APIKey.id))
    return [APIKeyOut.model_validate(k) for k in result.scalars().all()]


@router.post("/api-keys", response_model=APIKeyOut, status_code=status.HTTP_201_CREATED)
async def create_api_key(
    payload: APIKeyCreate, db: AsyncSession = Depends(get_db), _: User = Depends(require_admin)
):
    api_lookup = hash_api_key_lookup(payload.raw_key)
    api_hash = hash_api_key(payload.raw_key)
    ak = APIKey(
        name=payload.name,
        api_key_lookup=api_lookup,
        api_key_hash=api_hash,
        is_active=True,
        is_admin=payload.is_admin,
    )
    db.add(ak)
    await db.commit()
    await db.refresh(ak)
    return ak


@router.delete("/api-keys/{key_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_api_key(
    key_id: int, db: AsyncSession = Depends(get_db), _: User = Depends(require_admin)
) -> None:
    ak = await db.get(APIKey, key_id)
    if ak is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="API key not found")
    ak.is_active = False
    db.add(ak)
    await db.commit()
