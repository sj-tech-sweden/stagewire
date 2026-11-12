"""Encrypted storage for the NetBox integration configuration.

Mirrors ``app.domains.stockwire.config``: the API token and webhook HMAC secret
are Fernet-encrypted at rest (derived from ``jwt_secret_key``) and kept in the
``AppSetting`` key/value store. Everything else is plain JSON.
"""

import base64
import hashlib
import json
import secrets

from cryptography.fernet import Fernet
from sqlalchemy import select

from app.core.config import get_settings
from app.domains.auth.models import AppSetting

NETBOX_INTEGRATION_KEY = "netbox_integration"

# Custom fields Stagewire writes onto NetBox objects so the two systems can find
# each other. ``stagewire_link`` is a URL-type field NetBox renders as a clickable
# link back into the exact Stagewire job/device view.
NETBOX_CF_JOB_ID = "stagewire_job_id"
NETBOX_CF_DEVICE_ID = "stagewire_device_id"
NETBOX_CF_SYNC_STATUS = "stagewire_sync_status"
NETBOX_CF_LINK = "stagewire_link"

# NetBox object types the custom fields and webhook attach to.
NETBOX_CF_CONTENT_TYPES = ["dcim.device", "ipam.ipaddress"]
NETBOX_WEBHOOK_CONTENT_TYPES = ["ipam.ipaddress", "dcim.device"]


def _fernet() -> Fernet:
    secret = get_settings().jwt_secret_key.encode("utf-8")
    key = base64.urlsafe_b64encode(hashlib.sha256(secret).digest())
    return Fernet(key)


def _encrypt(value: str) -> str:
    if not value:
        return ""
    return _fernet().encrypt(value.encode("utf-8")).decode("utf-8")


def _decrypt(token: str) -> str | None:
    if not token:
        return None
    try:
        return _fernet().decrypt(token.encode("utf-8")).decode("utf-8")
    except Exception:
        return None


async def _read_raw(db) -> dict:
    result = await db.execute(select(AppSetting).where(AppSetting.key == NETBOX_INTEGRATION_KEY))
    row = result.scalar_one_or_none()
    if row is None or not row.value:
        return {}
    try:
        stored = json.loads(row.value)
    except Exception:
        return {}
    return stored if isinstance(stored, dict) else {}


async def _write_raw(db, payload: dict) -> None:
    result = await db.execute(select(AppSetting).where(AppSetting.key == NETBOX_INTEGRATION_KEY))
    row = result.scalar_one_or_none()
    if row is None:
        db.add(AppSetting(key=NETBOX_INTEGRATION_KEY, value=json.dumps(payload)))
    else:
        row.value = json.dumps(payload)
    await db.commit()


async def load_integration_config(db) -> dict:
    """Return the merged NetBox integration config (secrets decrypted)."""
    default_base = get_settings().netbox_api_base_url
    stored = await _read_raw(db)
    enc_token = stored.get("api_token_enc")
    enc_secret = stored.get("webhook_secret_enc")
    decrypted_token = _decrypt(enc_token) if enc_token else None
    if not decrypted_token:
        decrypted_token = get_settings().netbox_api_token
    return {
        "enabled": bool(stored.get("enabled", False)),
        "base_url": (stored.get("base_url") or default_base).rstrip("/"),
        "api_token": decrypted_token,
        "tenant_slug": stored.get("tenant_slug") or "",
        "site_slug": stored.get("site_slug") or "",
        "device_role_slug": stored.get("device_role_slug") or "stagewire",
        # NetBox device_type has no slug; we reference it by id (filled in by
        # ``ensure_provisioning`` when it creates the default type).
        "device_type_id": stored.get("device_type_id"),
        "default_device_status": stored.get("default_device_status") or "staged",
        "public_url": (stored.get("public_url") or "").rstrip("/"),
        "webhook_secret": _decrypt(enc_secret) if enc_secret else None,
    }


async def save_integration_config(
    db,
    *,
    enabled: bool,
    base_url: str,
    api_token: str | None,
    tenant_slug: str | None = None,
    site_slug: str | None = None,
    device_role_slug: str | None = None,
    device_type_id: int | None = None,
    default_device_status: str | None = None,
    public_url: str | None = None,
) -> dict:
    stored = await _read_raw(db)
    existing = await load_integration_config(db)
    new_token = api_token if api_token not in (None, "") else existing.get("api_token")
    payload = {
        **stored,
        "enabled": bool(enabled),
        "base_url": base_url or get_settings().netbox_api_base_url,
        "api_token_enc": _encrypt(new_token) if new_token else "",
        "tenant_slug": tenant_slug if tenant_slug is not None else existing["tenant_slug"],
        "site_slug": site_slug if site_slug is not None else existing["site_slug"],
        "device_role_slug": (
            device_role_slug if device_role_slug is not None else existing["device_role_slug"]
        ),
        "device_type_id": (
            device_type_id if device_type_id is not None else existing["device_type_id"]
        ),
        "default_device_status": (
            default_device_status
            if default_device_status is not None
            else existing["default_device_status"]
        ),
        "public_url": (public_url if public_url is not None else existing["public_url"]).rstrip(
            "/"
        ),
    }
    await _write_raw(db, payload)
    return payload


async def save_webhook_secret(db, secret: str) -> None:
    stored = await _read_raw(db)
    stored["webhook_secret_enc"] = _encrypt(secret)
    await _write_raw(db, stored)


def generate_webhook_secret() -> str:
    return secrets.token_hex(32)
