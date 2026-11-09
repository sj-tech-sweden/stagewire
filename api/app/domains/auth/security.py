import hashlib
import os
import secrets
from datetime import UTC, datetime, timedelta

import bcrypt
import jwt

from app.core.config import get_settings

settings = get_settings()


def generate_refresh_token() -> str:
    return secrets.token_urlsafe(48)


def compute_refresh_token_hash(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def _get_password_pepper_bytes() -> bytes:
    pepper = os.getenv("PASSWORD_PEPPER")
    if pepper:
        return pepper.encode("utf-8")
    if settings.app_env.lower() in {"development", "test"}:
        return b"stagewire-default-password-pepper"
    raise RuntimeError("PASSWORD_PEPPER must be set outside development/test environments")


def hash_password(password: str) -> str:
    pw = password.encode("utf-8")
    if len(pw) > 72:
        pw = hashlib.pbkdf2_hmac("sha256", pw, _get_password_pepper_bytes(), 310_000, dklen=32)
    return bcrypt.hashpw(pw, bcrypt.gensalt()).decode("utf-8")


def verify_password(plain: str, hashed: str) -> bool:
    try:
        return bcrypt.checkpw(plain.encode("utf-8"), hashed.encode("utf-8"))
    except Exception:
        return False


def create_access_token(user_id: int, email: str, role: str) -> str:
    expire = datetime.now(UTC) + timedelta(minutes=settings.jwt_access_expire_minutes)
    payload = {
        "sub": str(user_id),
        "email": email,
        "role": role,
        "exp": expire,
        "iat": datetime.now(UTC),
    }
    return jwt.encode(payload, settings.jwt_secret_key, algorithm=settings.jwt_algorithm)


def decode_token(token: str) -> dict:
    return jwt.decode(token, settings.jwt_secret_key, algorithms=[settings.jwt_algorithm])


def create_share_token(job_id: str | int, *, ttl_minutes: int | None = None) -> str:
    """Mint a read-only, login-free share token for the day-of-show crew view.

    The token carries only the job id and a ``view`` scope, so it can neither write
    nor read anything outside that job. A logged-in user mints it; a crew member
    then opens the mobile view with it and no session.
    """
    if ttl_minutes is None:
        ttl_minutes = settings.share_token_ttl_minutes
    payload: dict = {
        "job_id": str(job_id),
        "scope": "view",
        "iat": datetime.now(UTC),
    }
    if ttl_minutes and ttl_minutes > 0:
        payload["exp"] = datetime.now(UTC) + timedelta(minutes=ttl_minutes)
    return jwt.encode(payload, settings.jwt_secret_key, algorithm=settings.jwt_algorithm)


def verify_share_token(token: str) -> dict:
    """Validate a share token; returns its claims or raises ``ValueError``."""
    try:
        claims = jwt.decode(token, settings.jwt_secret_key, algorithms=[settings.jwt_algorithm])
    except jwt.PyJWTError as exc:  # expired / tampered / malformed
        raise ValueError("Invalid or expired share token") from exc
    if claims.get("scope") != "view":
        raise ValueError("Share token is not view-scoped")
    if "job_id" not in claims:
        raise ValueError("Share token is missing its job id")
    return claims


def _get_api_key_pepper() -> str:
    pepper = os.getenv("API_KEY_PEPPER")
    if pepper:
        return pepper
    if settings.app_env.lower() in {"development", "test"}:
        return "stagewire-default-api-key-pepper"
    raise RuntimeError("API_KEY_PEPPER must be set outside development/test environments")


def hash_api_key(raw: str) -> str:
    pepper = _get_api_key_pepper()
    salt = secrets.token_bytes(16)
    dk = hashlib.pbkdf2_hmac("sha256", f"{raw}{pepper}".encode(), salt, 310_000)
    return f"pbkdf2_sha256$310000${salt.hex()}${dk.hex()}"


def hash_api_key_lookup(raw: str) -> str:
    pepper = _get_api_key_pepper()
    dk = hashlib.pbkdf2_hmac("sha256", raw.encode("utf-8"), pepper.encode("utf-8"), 1)
    return dk.hex()


def verify_api_key_hash(raw: str, stored_hash: str) -> bool:
    try:
        parts = stored_hash.split("$")
        if len(parts) != 4:
            return False
        algorithm, iterations_raw, salt_hex, expected_hex = parts
        if algorithm != "pbkdf2_sha256":
            return False
        salt = bytes.fromhex(salt_hex)
        expected = bytes.fromhex(expected_hex)
        dk = hashlib.pbkdf2_hmac(
            "sha256", f"{raw}{_get_api_key_pepper()}".encode(), salt, int(iterations_raw)
        )
        return secrets.compare_digest(dk, expected)
    except (TypeError, ValueError):
        return False
