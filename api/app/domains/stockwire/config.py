import base64
import hashlib
import json

from cryptography.fernet import Fernet
from sqlalchemy import select

from app.core.config import get_settings
from app.domains.auth.models import AppSetting

STOCKWIRE_INTEGRATION_KEY = "stockwire_integration"
STOCKWIRE_CATEGORY_MAP_KEY = "stockwire_category_map"

GEAR_TYPES = [
    "microphone",
    "di",
    "wireless",
    "stagebox",
    "mixer",
    "speaker",
    "monitor",
    "stand",
    "recorder",
    "amp",
    "other",
]


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


STAGEWIRE_RENTAL_INSTANCE_ID = "stagewire-main"


async def _read_integration_raw(db) -> dict:
    result = await db.execute(select(AppSetting).where(AppSetting.key == STOCKWIRE_INTEGRATION_KEY))
    row = result.scalar_one_or_none()
    if row is None or not row.value:
        return {}
    try:
        stored = json.loads(row.value)
    except Exception:
        return {}
    return stored if isinstance(stored, dict) else {}


async def _write_integration_raw(db, payload: dict) -> None:
    result = await db.execute(select(AppSetting).where(AppSetting.key == STOCKWIRE_INTEGRATION_KEY))
    row = result.scalar_one_or_none()
    if row is None:
        db.add(AppSetting(key=STOCKWIRE_INTEGRATION_KEY, value=json.dumps(payload)))
    else:
        row.value = json.dumps(payload)
    await db.commit()


async def load_integration_config(db) -> dict:
    default_base = get_settings().stockwire_api_base_url
    stored = await _read_integration_raw(db)
    enc = stored.get("api_key_enc")
    secret_enc = stored.get("deeplink_secret_enc")
    return {
        "enabled": bool(stored.get("enabled", False)),
        "base_url": stored.get("base_url") or default_base,
        "api_key": _decrypt(enc) if enc else None,
        # URL under which stockwire-rental reaches this Stagewire API.
        "public_url": (stored.get("public_url") or "").rstrip("/"),
        # Shared HMAC secret for deeplinks, pushed to stockwire-rental on connect.
        "deeplink_secret": _decrypt(secret_enc) if secret_enc else None,
    }


async def save_integration_config(
    db,
    *,
    enabled: bool,
    base_url: str,
    api_key: str | None,
    public_url: str | None = None,
) -> dict:
    stored = await _read_integration_raw(db)
    existing = await load_integration_config(db)
    new_key = api_key if api_key not in (None, "") else existing.get("api_key")
    payload = {
        **stored,
        "enabled": bool(enabled),
        "base_url": base_url or get_settings().stockwire_api_base_url,
        "api_key_enc": _encrypt(new_key) if new_key else "",
        "public_url": (public_url if public_url is not None else existing["public_url"]).rstrip(
            "/"
        ),
    }
    await _write_integration_raw(db, payload)
    return payload


async def save_deeplink_secret(db, secret: str) -> None:
    stored = await _read_integration_raw(db)
    stored["deeplink_secret_enc"] = _encrypt(secret)
    await _write_integration_raw(db, stored)


async def load_category_map(db) -> dict:
    """Map of stockwire `category` string -> Stagewire gear type."""
    result = await db.execute(
        select(AppSetting).where(AppSetting.key == STOCKWIRE_CATEGORY_MAP_KEY)
    )
    row = result.scalar_one_or_none()
    if not row or not row.value:
        return {}
    try:
        data = json.loads(row.value)
    except Exception:
        return {}
    return data if isinstance(data, dict) else {}


async def save_category_map(db, mapping: dict) -> dict:
    cleaned: dict = {}
    for category, gear_type in (mapping or {}).items():
        if category and gear_type in GEAR_TYPES:
            cleaned[str(category)] = gear_type
    result = await db.execute(
        select(AppSetting).where(AppSetting.key == STOCKWIRE_CATEGORY_MAP_KEY)
    )
    row = result.scalar_one_or_none()
    if row is None:
        db.add(AppSetting(key=STOCKWIRE_CATEGORY_MAP_KEY, value=json.dumps(cleaned)))
    else:
        row.value = json.dumps(cleaned)
    await db.commit()
    return cleaned


def gear_types_for_categories(category_map: dict, gear_type: str) -> list[str]:
    """Stockwire categories mapped to the given Stagewire gear type."""
    return [cat for cat, gt in category_map.items() if gt == gear_type]
