import secrets
import time

import httpx
from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel

from app.core.db import get_db
from app.domains.auth.deps import require_admin
from app.domains.auth.models import AppSetting
from app.domains.stockwire.config import (
    GEAR_TYPES,
    STAGEWIRE_RENTAL_INSTANCE_ID,
    load_category_map,
    load_integration_config,
    save_category_map,
    save_deeplink_secret,
    save_integration_config,
)

router = APIRouter(prefix="/settings", tags=["settings"])

COMPANY_SETTINGS_KEY = "company_settings"
DEFAULT_LANGUAGE = "en"


class StockwireIntegrationOut(BaseModel):
    enabled: bool = False
    base_url: str = ""
    has_api_key: bool = False
    public_url: str = ""
    deeplink_ready: bool = False


class StockwireRentalConnectResult(BaseModel):
    ok: bool = False
    code: str = ""
    message: str = ""
    instance_id: str = ""


class StockwireIntegrationUpdate(BaseModel):
    enabled: bool = False
    base_url: str
    api_key: str | None = None
    public_url: str | None = None


class StockwireTestResult(BaseModel):
    ok: bool
    status: int | None = None
    latency_ms: int | None = None
    detail: str = ""


class CompanySettingsOut(BaseModel):
    default_language: str = DEFAULT_LANGUAGE


class CompanySettingsUpdate(BaseModel):
    default_language: str = DEFAULT_LANGUAGE


async def load_company_settings(db) -> dict:
    from sqlalchemy import select

    result = await db.execute(select(AppSetting).where(AppSetting.key == COMPANY_SETTINGS_KEY))
    row = result.scalar_one_or_none()
    if row is None:
        return {"default_language": DEFAULT_LANGUAGE}
    try:
        import json

        data = json.loads(row.value)
    except Exception:
        return {"default_language": DEFAULT_LANGUAGE}
    if not isinstance(data, dict):
        return {"default_language": DEFAULT_LANGUAGE}
    return {"default_language": str(data.get("default_language") or DEFAULT_LANGUAGE)}


@router.get("/company", response_model=CompanySettingsOut)
async def get_company_settings(db=Depends(get_db)) -> CompanySettingsOut:
    return CompanySettingsOut(**await load_company_settings(db))


@router.put("/company", response_model=CompanySettingsOut)
async def update_company_settings(
    payload: CompanySettingsUpdate,
    db=Depends(get_db),
    _=Depends(require_admin),
) -> CompanySettingsOut:
    import json

    current = await load_company_settings(db)
    data = {"default_language": payload.default_language or current["default_language"]}
    value = json.dumps(data)
    from sqlalchemy import select

    result = await db.execute(select(AppSetting).where(AppSetting.key == COMPANY_SETTINGS_KEY))
    row = result.scalar_one_or_none()
    if row is None:
        db.add(AppSetting(key=COMPANY_SETTINGS_KEY, value=value))
    else:
        row.value = value
    await db.commit()
    return CompanySettingsOut(**data)


@router.get("/stockwire", response_model=StockwireIntegrationOut)
async def get_stockwire_integration(
    db=Depends(get_db), _=Depends(require_admin)
) -> StockwireIntegrationOut:
    cfg = await load_integration_config(db)
    return _stockwire_out(cfg)


def _stockwire_out(cfg: dict) -> StockwireIntegrationOut:
    return StockwireIntegrationOut(
        enabled=cfg["enabled"],
        base_url=cfg["base_url"],
        has_api_key=bool(cfg["api_key"]),
        public_url=cfg["public_url"],
        deeplink_ready=bool(cfg["deeplink_secret"]),
    )


@router.put("/stockwire", response_model=StockwireIntegrationOut)
async def update_stockwire_integration(
    payload: StockwireIntegrationUpdate,
    db=Depends(get_db),
    _=Depends(require_admin),
) -> StockwireIntegrationOut:
    await save_integration_config(
        db,
        enabled=payload.enabled,
        base_url=payload.base_url,
        api_key=payload.api_key,
        public_url=payload.public_url,
    )
    cfg = await load_integration_config(db)
    return _stockwire_out(cfg)


@router.post("/stockwire/connect-rental", response_model=StockwireRentalConnectResult)
async def connect_stockwire_rental(
    db=Depends(get_db), _=Depends(require_admin)
) -> StockwireRentalConnectResult:
    """Register this Stagewire with stockwire-rental and verify it.

    1. Creates the shared deeplink secret if missing.
    2. Registers this Stagewire on stockwire-rental via its public register endpoint
       (base_url + shared key), so rental can call back and verify deeplinks.
    3. If an admin API key is saved, runs rental's connection test back to Stagewire.
    """
    cfg = await load_integration_config(db)
    if not cfg["base_url"]:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Set the stockwire-rental base URL first")
    if not cfg["public_url"]:
        raise HTTPException(
            status.HTTP_400_BAD_REQUEST,
            "Set the Stagewire URL that stockwire-rental can reach first",
        )
    secret = cfg["deeplink_secret"]
    if not secret:
        secret = secrets.token_hex(32)
        await save_deeplink_secret(db, secret)

    base = cfg["base_url"].rstrip("/")
    register_url = f"{base}/api/v1/settings/integrations/stagewire/register"
    instances_url = f"{base}/api/v1/settings/integrations/stagewire-instances"
    try:
        async with httpx.AsyncClient(timeout=15.0) as client:
            reg = await client.post(
                register_url,
                json={
                    "instance_id": STAGEWIRE_RENTAL_INSTANCE_ID,
                    "name": "Stagewire",
                    "base_url": cfg["public_url"],
                    "api_key": secret,
                },
            )
            if reg.status_code >= 400:
                detail = ""
                try:
                    detail = str(reg.json().get("detail") or "")
                except ValueError:
                    detail = reg.text[:200]
                return StockwireRentalConnectResult(
                    ok=False,
                    code="register_failed",
                    message=(
                        "stockwire-rental rejected the registration "
                        f"(HTTP {reg.status_code}): {detail}"
                    ),
                )
            if not cfg["api_key"]:
                return StockwireRentalConnectResult(
                    ok=True,
                    code="registered_untested",
                    instance_id=STAGEWIRE_RENTAL_INSTANCE_ID,
                    message="Registered on stockwire-rental. Test skipped: no admin API key saved.",
                )
            headers = {"Authorization": f"Bearer {cfg['api_key']}", "Accept": "application/json"}
            tested = await client.post(
                f"{instances_url}/{STAGEWIRE_RENTAL_INSTANCE_ID}/test", headers=headers
            )
            verdict = tested.json() if tested.status_code == 200 else {}
    except httpx.HTTPError as exc:
        return StockwireRentalConnectResult(
            ok=False,
            code="unreachable",
            message=f"Could not reach stockwire-rental: {type(exc).__name__}",
        )

    if verdict.get("ok"):
        return StockwireRentalConnectResult(
            ok=True,
            code="connected",
            instance_id=STAGEWIRE_RENTAL_INSTANCE_ID,
            message="Connected. stockwire-rental can reach Stagewire.",
        )
    return StockwireRentalConnectResult(
        ok=False,
        code="test_failed",
        instance_id=STAGEWIRE_RENTAL_INSTANCE_ID,
        message=str(verdict.get("message") or "no response"),
    )


def _flatten_tree_count(tree: list) -> list:
    out: list = []
    stack = list(tree or [])
    while stack:
        node = stack.pop()
        out.append(node)
        stack.extend(node.get("children") or [])
    return out


@router.post("/stockwire/test", response_model=StockwireTestResult)
async def test_stockwire_integration(
    db=Depends(get_db), _=Depends(require_admin)
) -> StockwireTestResult:
    cfg = await load_integration_config(db)
    if not cfg.get("api_key"):
        return StockwireTestResult(ok=False, detail="No API key configured")
    url = f"{cfg['base_url'].rstrip('/')}/api/v1/health/ready"
    headers = {
        "Accept": "application/json",
        "Authorization": f"Bearer {cfg['api_key']}",
    }
    try:
        start = time.monotonic()
        async with httpx.AsyncClient(headers=headers, timeout=10.0) as client:
            resp = await client.get(url)
        latency = int((time.monotonic() - start) * 1000)
        if resp.status_code != 200:
            return StockwireTestResult(
                ok=False,
                status=resp.status_code,
                latency_ms=latency,
                detail=f"Health check failed: HTTP {resp.status_code}",
            )
        async with httpx.AsyncClient(headers=headers, timeout=10.0) as client:
            auth_resp = await client.get(
                f"{cfg['base_url'].rstrip('/')}/api/v1/inventory/categories/tree"
            )
        if auth_resp.status_code in (401, 403):
            return StockwireTestResult(
                ok=False,
                status=auth_resp.status_code,
                latency_ms=latency,
                detail="Reached stockwire-rental but the API key was rejected (HTTP "
                f"{auth_resp.status_code}). Check the key.",
            )
        if auth_resp.status_code != 200:
            return StockwireTestResult(
                ok=False,
                status=auth_resp.status_code,
                latency_ms=latency,
                detail=f"Authenticated call failed: HTTP {auth_resp.status_code}",
            )
        categories = len(_flatten_tree_count(auth_resp.json()))
        return StockwireTestResult(
            ok=True,
            status=200,
            latency_ms=latency,
            detail=f"Connected and authenticated · {categories} product categories",
        )
    except httpx.ConnectError:
        return StockwireTestResult(
            ok=False,
            detail=(
                f"Could not reach {url} — check the API base URL and that "
                "Stagewire can reach it from its container "
                "(use host.docker.internal instead of localhost in local Docker)."
            ),
        )
    except httpx.ConnectTimeout:
        return StockwireTestResult(ok=False, detail=f"Timed out connecting to {url}.")
    except Exception as exc:  # noqa: BLE001 - surface upstream errors to caller
        return StockwireTestResult(ok=False, detail=str(exc))


class CategoryMapOut(BaseModel):
    mapping: dict = {}
    gear_types: list[str] = []


@router.get("/stockwire/gear-types", response_model=CategoryMapOut)
async def get_gear_types(db=Depends(get_db), _=Depends(require_admin)) -> CategoryMapOut:
    return CategoryMapOut(mapping=await load_category_map(db), gear_types=list(GEAR_TYPES))


@router.get("/stockwire/category-map", response_model=CategoryMapOut)
async def get_category_map(db=Depends(get_db), _=Depends(require_admin)) -> CategoryMapOut:
    return CategoryMapOut(mapping=await load_category_map(db), gear_types=list(GEAR_TYPES))


class CategoryMapUpdate(BaseModel):
    mapping: dict = {}


@router.put("/stockwire/category-map", response_model=CategoryMapOut)
async def update_category_map(
    payload: CategoryMapUpdate, db=Depends(get_db), _=Depends(require_admin)
) -> CategoryMapOut:
    mapping = await save_category_map(db, payload.mapping)
    return CategoryMapOut(mapping=mapping, gear_types=list(GEAR_TYPES))
