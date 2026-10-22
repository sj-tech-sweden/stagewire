from fastapi import Depends, HTTPException, Request, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from jwt import PyJWTError as JWTError
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.db import get_db
from app.domains.auth.models import APIKey, User
from app.domains.auth.security import (
    decode_token,
    hash_api_key_lookup,
    verify_api_key_hash,
)

bearer = HTTPBearer(auto_error=False)


async def get_current_user(
    request: Request,
    creds: HTTPAuthorizationCredentials | None = Depends(bearer),
    db: AsyncSession = Depends(get_db),
) -> User:
    token = creds.credentials if creds else None
    if token:
        try:
            payload = decode_token(token)
            user_id = int(payload["sub"])
            user = await db.get(User, user_id)
            if user is None or not user.is_active:
                raise HTTPException(
                    status_code=status.HTTP_401_UNAUTHORIZED,
                    detail="User not found or inactive",
                )
            return user
        except (JWTError, KeyError, ValueError):
            pass

    api_key_raw = request.headers.get("X-API-Key") or token
    if api_key_raw:
        api_lookup = hash_api_key_lookup(api_key_raw)
        result = await db.execute(
            select(APIKey).where(
                APIKey.is_active.is_(True),
                APIKey.is_admin.is_(True),
                APIKey.api_key_lookup == api_lookup,
            )
        )
        for candidate in result.scalars().all():
            if verify_api_key_hash(api_key_raw, candidate.api_key_hash):
                return User(
                    id=0,
                    email=f"api-key:{candidate.name}",
                    password_hash="",
                    full_name=candidate.name,
                    role="admin",
                    is_active=True,
                    is_admin=True,
                    auth_source="apikey",
                )
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid API key")

    raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Credentials not provided")


def require_admin(current_user: User = Depends(get_current_user)) -> User:
    if not current_user or current_user.role != "admin":
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Admin role required")
    return current_user


def require_editor(current_user: User = Depends(get_current_user)) -> User:
    if not current_user or current_user.role not in {"admin", "manager"}:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Editor role required")
