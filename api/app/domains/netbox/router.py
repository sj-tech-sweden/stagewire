"""NetBox integration HTTP surface.

Two routers share the ``/api/v1/netbox`` prefix: the authenticated one for
configuration, testing, provisioning, device sync and IP assignment, and a
public one that only exposes the webhook callback (NetBox cannot authenticate
as a Stagewire user, so it is protected by the webhook HMAC signature instead).
"""

import json
import time
import uuid

import httpx
from fastapi import APIRouter, Depends, HTTPException, Query, Request, status

from app.core.db import get_db
from app.domains.auth.deps import get_current_user, require_admin
from app.domains.netbox import config as netbox_config
from app.domains.netbox import service
from app.domains.netbox.client import NetboxClient
from app.domains.netbox.schemas import (
    NetboxAssignIpRequest,
    NetboxAssignIpResult,
    NetboxAvailableIp,
    NetboxIntegrationOut,
    NetboxIntegrationUpdate,
    NetboxPrefix,
    NetboxProvisionResult,
    NetboxSyncResult,
    NetboxTestResult,
    NetboxVlan,
)
from app.domains.netbox.webhook import verify_netbox_signature

router = APIRouter(prefix="/netbox", tags=["netbox"], dependencies=[Depends(get_current_user)])
public_router = APIRouter(prefix="/netbox", tags=["netbox"])


def _config_out(cfg: dict) -> NetboxIntegrationOut:
    return NetboxIntegrationOut(
        enabled=cfg["enabled"],
        base_url=cfg["base_url"],
        has_api_token=bool(cfg["api_token"]),
        tenant_slug=cfg["tenant_slug"],
        site_slug=cfg["site_slug"],
        device_role_slug=cfg["device_role_slug"],
        device_type_id=cfg["device_type_id"],
        default_device_status=cfg["default_device_status"],
        public_url=cfg["public_url"],
        webhook_ready=bool(cfg["webhook_secret"] and cfg["public_url"]),
    )


@router.get("", response_model=NetboxIntegrationOut)
async def get_netbox_integration(
    db=Depends(get_db), _=Depends(require_admin)
) -> NetboxIntegrationOut:
    return _config_out(await netbox_config.load_integration_config(db))


@router.put("", response_model=NetboxIntegrationOut)
async def update_netbox_integration(
    payload: NetboxIntegrationUpdate,
    db=Depends(get_db),
    _=Depends(require_admin),
) -> NetboxIntegrationOut:
    await netbox_config.save_integration_config(
        db,
        enabled=payload.enabled,
        base_url=payload.base_url,
        api_token=payload.api_token,
        tenant_slug=payload.tenant_slug,
        site_slug=payload.site_slug,
        device_role_slug=payload.device_role_slug,
        device_type_id=payload.device_type_id,
        default_device_status=payload.default_device_status,
        public_url=payload.public_url,
    )
    return _config_out(await netbox_config.load_integration_config(db))


@router.post("/test", response_model=NetboxTestResult)
async def test_netbox_integration(db=Depends(get_db), _=Depends(require_admin)) -> NetboxTestResult:
    cfg = await netbox_config.load_integration_config(db)
    if not cfg.get("api_token") or not cfg["base_url"]:
        return NetboxTestResult(ok=False, detail="No API token or base URL configured")
    try:
        start = time.monotonic()
        # Build the client explicitly so the Authorization header is correct for
        # NetBox 4.7 (v2 `Bearer nbt_<key>.<token>`). The legacy v1 `Token
        # <token>` scheme is rejected, and we must not double-prefix a token that
        # already carries a `Bearer ` prefix (as the seed script emits).
        nb = NetboxClient(base_url=cfg["base_url"], token=cfg["api_token"])
        async with nb._client() as client:
            # /api/status/ requires authentication in NetBox 4.7, so this call
            # also validates the token, not just connectivity.
            resp = await client.get("/api/status/")
        latency = int((time.monotonic() - start) * 1000)
        if resp.status_code != 200:
            return NetboxTestResult(
                ok=False,
                status=resp.status_code,
                latency_ms=latency,
                detail=f"NetBox status check failed: HTTP {resp.status_code}",
            )
        async with nb._client() as client:
            auth_resp = await client.get("/api/dcim/devices/?limit=1")
        if auth_resp.status_code in (401, 403):
            return NetboxTestResult(
                ok=False,
                status=auth_resp.status_code,
                latency_ms=latency,
                detail="Reached NetBox but the token was rejected.",
            )
        if auth_resp.status_code != 200:
            return NetboxTestResult(
                ok=False,
                status=auth_resp.status_code,
                latency_ms=latency,
                detail=f"Authenticated call failed: HTTP {auth_resp.status_code}",
            )
        return NetboxTestResult(
            ok=True, status=200, latency_ms=latency, detail="Connected and authenticated"
        )
    except httpx.ConnectError:
        return NetboxTestResult(
            ok=False,
            detail="Could not reach NetBox — check the base URL and that Stagewire can reach it "
            "(use host.docker.internal instead of localhost in local Docker).",
        )
    except httpx.ConnectTimeout:
        return NetboxTestResult(ok=False, detail="Timed out connecting to NetBox.")
    except Exception as exc:  # noqa: BLE001 - surface upstream errors to caller
        return NetboxTestResult(ok=False, detail=str(exc))


@router.post("/provision", response_model=NetboxProvisionResult)
async def provision_netbox(db=Depends(get_db), _=Depends(require_admin)) -> NetboxProvisionResult:
    return await service.provision(db)


@router.post("/sync-job/{job_id}", response_model=NetboxSyncResult)
async def sync_job(
    job_id: uuid.UUID, db=Depends(get_db), _=Depends(require_admin)
) -> NetboxSyncResult:
    return await service.sync_job(db, job_id)


@router.post("/sync-venue/{venue_id}", response_model=NetboxSyncResult)
async def sync_venue(
    venue_id: uuid.UUID, db=Depends(get_db), _=Depends(require_admin)
) -> NetboxSyncResult:
    """Mirror a venue's Standard Base Rig into NetBox (see service.sync_venue)."""
    return await service.sync_venue(db, venue_id)


@router.get("/available-ips", response_model=list[NetboxAvailableIp])
async def available_ips(
    prefix: str = Query(..., description="CIDR prefix to draw available addresses from"),
    db=Depends(get_db),
) -> list[NetboxAvailableIp]:
    nb = await service.get_client(db)
    if nb is None:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "NetBox is not configured")
    prefix_obj = await nb.find_prefix(prefix)
    if prefix_obj is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, f"No NetBox prefix matches {prefix}")
    rows = await nb.available_ips(int(prefix_obj["id"]))
    return [NetboxAvailableIp(address=r["address"], family=r.get("family", 4)) for r in rows]


@router.get("/vlans", response_model=list[NetboxVlan])
async def list_vlans(db=Depends(get_db)) -> list[NetboxVlan]:
    """Browse NetBox VLANs. Scoped to the configured tenant/site when set."""
    nb = await service.get_client(db)
    if nb is None:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "NetBox is not configured")
    cfg = await netbox_config.load_integration_config(db)
    return await nb.list_vlans(
        tenant_slug=cfg.get("tenant_slug") or None,
        site_slug=cfg.get("site_slug") or None,
    )


@router.get("/prefixes", response_model=list[NetboxPrefix])
async def list_prefixes(
    vlan_id: int | None = Query(None, description="Filter to prefixes in this VLAN"),
    db=Depends(get_db),
) -> list[NetboxPrefix]:
    """Browse NetBox prefixes, optionally filtered to a VLAN. Scoped to the
    configured tenant/site when set. This is the 'subnet' step of the VLAN →
    subnet picker used when assigning an IP to a device."""
    nb = await service.get_client(db)
    if nb is None:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "NetBox is not configured")
    cfg = await netbox_config.load_integration_config(db)
    return await nb.list_prefixes(
        vlan_id=vlan_id,
        tenant_slug=cfg.get("tenant_slug") or None,
        site_slug=cfg.get("site_slug") or None,
    )


@router.post("/assign-ip", response_model=NetboxAssignIpResult)
async def assign_ip(payload: NetboxAssignIpRequest, db=Depends(get_db)) -> NetboxAssignIpResult:
    try:
        device_id = uuid.UUID(payload.device_id)
    except ValueError:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Invalid device_id") from None
    # Resolve the job the device belongs to so we can tag + broadcast correctly.
    from sqlalchemy import select

    from app.domains.graph.models import GraphDevice

    result = await db.execute(select(GraphDevice).where(GraphDevice.id == device_id))
    device = result.scalar_one_or_none()
    if device is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Device not found")
    job_id = device.job_id
    if job_id is None:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Device is not part of a job")
    return await service.assign_ip(
        db,
        job_id,
        device_id,
        prefix=payload.prefix,
        address=payload.address,
        description=payload.description,
    )


@public_router.post("/webhook")
async def netbox_webhook(request: Request, db=Depends(get_db)) -> dict:
    raw = await request.body()
    cfg = await netbox_config.load_integration_config(db)
    secret = cfg.get("webhook_secret")
    signature = request.headers.get("X-Hook-Signature")
    if not verify_netbox_signature(secret or "", raw, signature):
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Invalid webhook signature")
    try:
        payload = json.loads(raw or b"{}")
    except ValueError:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Invalid JSON body") from None
    return await service.handle_webhook(db, payload)
