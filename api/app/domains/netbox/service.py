"""NetBox integration orchestration: provisioning, device mirroring, IP assignment
and inbound webhook handling.

All functions take the active ``db`` session and degrade gracefully: when the
integration is disabled or unconfigured they raise ``RuntimeError`` with a clear
message rather than silently doing nothing, so the UI can surface the state.
"""

import uuid

from sqlalchemy import select

from app.domains.audio.ws import publish_job_event
from app.domains.graph.models import GraphDevice
from app.domains.netbox import config as netbox_config
from app.domains.netbox.client import NetboxClient
from app.domains.netbox.config import (
    NETBOX_CF_DEVICE_ID,
    NETBOX_CF_JOB_ID,
    NETBOX_CF_LINK,
    NETBOX_CF_SYNC_STATUS,
    NETBOX_CF_VENUE_ID,
)
from app.domains.netbox.schemas import (
    NetboxAssignIpResult,
    NetboxProvisionResult,
    NetboxSyncResult,
)

WEBHOOK_NAME = "stagewire-sync"
WEBHOOK_PATH = "/api/v1/netbox/webhook"

# Keys we read/write on a device's local ``attributes`` bag.
ATTR_NETBOX_DEVICE_ID = "netbox_device_id"
ATTR_NETBOX_URL = "netbox_url"
ATTR_NETBOX_SYNC_STATUS = "netbox_sync_status"
ATTR_NETBOX_IP_ID = "netbox_ip_id"
ATTR_NETBOX_LINK = "netbox_link"


def _stagewire_link(
    public_url: str,
    *,
    job_id: uuid.UUID | None = None,
    venue_id: uuid.UUID | None = None,
    device_id: uuid.UUID,
) -> str:
    base = (public_url or "").rstrip("/")
    if not base:
        return ""
    if job_id is not None:
        return f"{base}/jobs/{job_id}?device={device_id}"
    if venue_id is not None:
        return f"{base}/venues/{venue_id}?device={device_id}"
    return ""


def _device_custom_fields(
    *,
    job_id: uuid.UUID | None = None,
    venue_id: uuid.UUID | None = None,
    device_id: uuid.UUID,
    link: str,
    status: str,
) -> dict:
    # Exactly one scope is set: a job-synced device carries stagewire_job_id, a
    # venue base-rig device carries stagewire_venue_id. Both reference the same
    # stagewire_device_id (the GraphDevice id) so NetBox→Stagewire webhooks resolve
    # the local device regardless of which scope created it.
    if job_id is None and venue_id is None:
        raise ValueError("a NetBox device needs a job_id or venue_id scope")
    cf: dict = {
        NETBOX_CF_DEVICE_ID: str(device_id),
        NETBOX_CF_SYNC_STATUS: status,
    }
    if job_id is not None:
        cf[NETBOX_CF_JOB_ID] = str(job_id)
    if venue_id is not None:
        cf[NETBOX_CF_VENUE_ID] = str(venue_id)
    if link:
        cf[NETBOX_CF_LINK] = link
    return cf


async def get_client(db) -> NetboxClient | None:
    cfg = await netbox_config.load_integration_config(db)
    if not cfg["api_token"]:
        return None
    return NetboxClient(base_url=cfg["base_url"], token=cfg["api_token"])


async def provision(db) -> NetboxProvisionResult:
    cfg = await netbox_config.load_integration_config(db)
    if not cfg["base_url"] or not cfg["api_token"]:
        return NetboxProvisionResult(
            ok=False, code="unconfigured", message="Set the NetBox base URL and API token first."
        )
    nb = NetboxClient(base_url=cfg["base_url"], token=cfg["api_token"])
    created: list[str] = []
    try:
        created += await nb.ensure_custom_fields()
        device_type_id = await nb.ensure_device_type("Stagewire Device", "Generic")
        await netbox_config.save_integration_config(
            db,
            enabled=cfg["enabled"],
            base_url=cfg["base_url"],
            api_token=cfg["api_token"],
            tenant_slug=cfg["tenant_slug"],
            site_slug=cfg["site_slug"],
            device_role_slug=cfg["device_role_slug"],
            device_type_id=device_type_id,
            default_device_status=cfg["default_device_status"],
            public_url=cfg["public_url"],
        )
        # Re-load so we have the freshly stored device_type_id.
        cfg = await netbox_config.load_integration_config(db)

        secret = cfg["webhook_secret"]
        if not secret:
            secret = netbox_config.generate_webhook_secret()
            await netbox_config.save_webhook_secret(db, secret)
        if cfg["public_url"]:
            callback = f"{cfg['public_url']}{WEBHOOK_PATH}"
            if await nb.ensure_webhook(WEBHOOK_NAME, callback, secret):
                created.append("webhook")
        else:
            return NetboxProvisionResult(
                ok=True,
                code="partial",
                message=(
                    "Custom fields and device type provisioned. Set the Stagewire "
                    "public URL to finish configuring the webhook."
                ),
                created=created,
            )
    except RuntimeError as exc:
        return NetboxProvisionResult(ok=False, code="netbox_error", message=str(exc))

    return NetboxProvisionResult(
        ok=True,
        code="provisioned",
        message="NetBox custom fields and webhook are configured.",
        created=created,
    )


async def sync_job(db, job_id: uuid.UUID) -> NetboxSyncResult:
    """Mirror a job's devices into NetBox, creating them on first sync."""
    cfg = await netbox_config.load_integration_config(db)
    if not cfg["enabled"]:
        return NetboxSyncResult(ok=False, message="NetBox integration is disabled.")
    nb = await get_client(db)
    if nb is None:
        return NetboxSyncResult(ok=False, message="NetBox is not configured.")

    # A device needs a site, a role and a device type to be created in NetBox. These
    # come from the integration config (site/role set in Settings, device_type_id from
    # provision). If any are missing, say so clearly instead of letting NetBox return a
    # 400 that would otherwise surface as a 500.
    if not (cfg["site_slug"] and cfg["device_role_slug"] and cfg["device_type_id"]):
        return NetboxSyncResult(
            ok=False,
            message=(
                "NetBox is missing required config (site, device role or device type). "
                "Set them in Settings → NetBox and run Provision before syncing."
            ),
        )

    result = await db.execute(select(GraphDevice).where(GraphDevice.job_id == job_id))
    devices = result.scalars().all()
    created = 0
    updated = 0

    try:
        # Ensure custom fields exist and are valid for dcim.device (self-heals fields
        # left stale by an older build), so device creation doesn't fail on them.
        await nb.ensure_custom_fields()

        for device in devices:
            attributes = dict(device.attributes or {})
            link = _stagewire_link(cfg["public_url"], job_id=job_id, device_id=device.id)
            cf = _device_custom_fields(job_id=job_id, device_id=device.id, link=link, status="ok")
            existing = await nb.find_device(str(device.id))
            if existing is None:
                created_device = await nb.create_device(
                    name=device.name or str(device.id),
                    site_slug=cfg["site_slug"],
                    device_type_id=int(cfg["device_type_id"] or 0),
                    role_slug=cfg["device_role_slug"],
                    status_slug=cfg["default_device_status"],
                    tenant_slug=cfg["tenant_slug"] or None,
                    custom_fields=cf,
                )
                attributes[ATTR_NETBOX_DEVICE_ID] = str(created_device["id"])
                attributes[ATTR_NETBOX_URL] = _device_web_url(cfg["base_url"], created_device)
                attributes[ATTR_NETBOX_LINK] = link
                attributes[ATTR_NETBOX_SYNC_STATUS] = "ok"
                created += 1
            else:
                await nb.update_device(
                    int(existing["id"]),
                    {"custom_fields": {**existing.get("custom_fields", {}), **cf}},
                )
                attributes[ATTR_NETBOX_DEVICE_ID] = str(existing["id"])
                attributes[ATTR_NETBOX_URL] = _device_web_url(cfg["base_url"], existing)
                attributes[ATTR_NETBOX_LINK] = link
                attributes[ATTR_NETBOX_SYNC_STATUS] = "ok"
                updated += 1
            device.attributes = attributes
    except RuntimeError as exc:
        # NetBox client raises RuntimeError on any non-2xx; surface it as a clean
        # result rather than a 500 so the UI can show the underlying NetBox error.
        return NetboxSyncResult(ok=False, message=f"NetBox sync failed: {exc}")

    await db.commit()
    return NetboxSyncResult(
        ok=True,
        devices_created=created,
        devices_updated=updated,
        message=f"Synced {created} new and updated {updated} existing NetBox devices.",
    )


async def sync_venue(db, venue_id: uuid.UUID) -> NetboxSyncResult:
    """Mirror a venue's Standard Base Rig into NetBox, creating devices on first sync.

    A venue base rig is the same ``GraphDevice`` graph a job uses, scoped by
    ``venue_id`` (with ``job_id IS NULL``). Mirroring it into NetBox follows the
    exact same shape as ``sync_job``; the only differences are the scope filter and
    the custom field we stamp (``stagewire_venue_id`` instead of ``stagewire_job_id``)
    so a venue-synced device links back to the venue rather than a job. The device
    back-reference (``stagewire_device_id``) is the same GraphDevice id either way,
    so NetBox→Stagewire webhook conflict detection works for both.
    """
    cfg = await netbox_config.load_integration_config(db)
    if not cfg["enabled"]:
        return NetboxSyncResult(ok=False, message="NetBox integration is disabled.")
    nb = await get_client(db)
    if nb is None:
        return NetboxSyncResult(ok=False, message="NetBox is not configured.")

    # A device needs a site, a role and a device type to be created in NetBox. These
    # come from the integration config (site/role set in Settings, device_type_id from
    # provision). If any are missing, say so clearly instead of letting NetBox return a
    # 400 that would otherwise surface as a 500.
    if not (cfg["site_slug"] and cfg["device_role_slug"] and cfg["device_type_id"]):
        return NetboxSyncResult(
            ok=False,
            message=(
                "NetBox is missing required config (site, device role or device type). "
                "Set them in Settings → NetBox and run Provision before syncing."
            ),
        )

    # The base rig is every device scoped to the venue with no job (a device cloned
    # onto a job keeps venue_id for editing but gains a job_id; the rig itself is the
    # job_id IS NULL set). This is the venue counterpart to ``GraphDevice.job_id == job_id``.
    result = await db.execute(
        select(GraphDevice).where(GraphDevice.venue_id == venue_id, GraphDevice.job_id.is_(None))
    )
    devices = result.scalars().all()
    created = 0
    updated = 0

    try:
        # Ensure custom fields exist and are valid for dcim.device (self-heals fields
        # left stale by an older build), so device creation doesn't fail on them.
        await nb.ensure_custom_fields()

        for device in devices:
            attributes = dict(device.attributes or {})
            link = _stagewire_link(cfg["public_url"], venue_id=venue_id, device_id=device.id)
            cf = _device_custom_fields(
                venue_id=venue_id, device_id=device.id, link=link, status="ok"
            )
            existing = await nb.find_device(str(device.id))
            if existing is None:
                created_device = await nb.create_device(
                    name=device.name or str(device.id),
                    site_slug=cfg["site_slug"],
                    device_type_id=int(cfg["device_type_id"] or 0),
                    role_slug=cfg["device_role_slug"],
                    status_slug=cfg["default_device_status"],
                    tenant_slug=cfg["tenant_slug"] or None,
                    custom_fields=cf,
                )
                attributes[ATTR_NETBOX_DEVICE_ID] = str(created_device["id"])
                attributes[ATTR_NETBOX_URL] = _device_web_url(cfg["base_url"], created_device)
                attributes[ATTR_NETBOX_LINK] = link
                attributes[ATTR_NETBOX_SYNC_STATUS] = "ok"
                created += 1
            else:
                await nb.update_device(
                    int(existing["id"]),
                    {"custom_fields": {**existing.get("custom_fields", {}), **cf}},
                )
                attributes[ATTR_NETBOX_DEVICE_ID] = str(existing["id"])
                attributes[ATTR_NETBOX_URL] = _device_web_url(cfg["base_url"], existing)
                attributes[ATTR_NETBOX_LINK] = link
                attributes[ATTR_NETBOX_SYNC_STATUS] = "ok"
                updated += 1
            device.attributes = attributes
    except RuntimeError as exc:
        # NetBox client raises RuntimeError on any non-2xx; surface it as a clean
        # result rather than a 500 so the UI can show the underlying NetBox error.
        return NetboxSyncResult(ok=False, message=f"NetBox sync failed: {exc}")

    await db.commit()
    return NetboxSyncResult(
        ok=True,
        devices_created=created,
        devices_updated=updated,
        message=f"Synced {created} new and updated {updated} existing NetBox devices.",
    )


def _device_web_url(base_url: str, netbox_device: dict) -> str:
    # Build the NetBox web-UI URL from the device id. NetBox's UI path for a device
    # is always ``/dcim/devices/{id}/``. Do NOT derive this from the ``display``
    # field: NetBox 4.7 returns ``display`` as a plain string (older versions
    # returned a dict with a ``url`` key), so ``display.get("url")`` raises
    # AttributeError. The top-level ``url`` is the *API* URL, not the UI URL.
    device_id = netbox_device.get("id")
    if device_id is None:
        return netbox_device.get("url") or ""
    return f"{base_url.rstrip('/')}/dcim/devices/{device_id}/"


async def assign_ip(
    db,
    job_id: uuid.UUID,
    device_id: uuid.UUID,
    *,
    prefix: str | None = None,
    address: str | None = None,
    description: str | None = None,
) -> NetboxAssignIpResult:
    cfg = await netbox_config.load_integration_config(db)
    if not cfg["enabled"]:
        return NetboxAssignIpResult(ok=False, message="NetBox integration is disabled.")
    nb = await get_client(db)
    if nb is None:
        return NetboxAssignIpResult(ok=False, message="NetBox is not configured.")

    result = await db.execute(select(GraphDevice).where(GraphDevice.id == device_id))
    device = result.scalar_one_or_none()
    if device is None:
        return NetboxAssignIpResult(ok=False, message="Device not found.")
    attributes = dict(device.attributes or {})

    # Ensure the device exists in NetBox first.
    netbox_device = await nb.find_device(str(device.id))
    link = _stagewire_link(cfg["public_url"], job_id=job_id, device_id=device.id)
    cf = _device_custom_fields(job_id=job_id, device_id=device.id, link=link, status="ok")
    if netbox_device is None:
        if not cfg["site_slug"]:
            return NetboxAssignIpResult(ok=False, message="Set the NetBox site before syncing.")
        created = await nb.create_device(
            name=device.name or str(device.id),
            site_slug=cfg["site_slug"],
            device_type_id=int(cfg["device_type_id"] or 0),
            role_slug=cfg["device_role_slug"],
            status_slug=cfg["default_device_status"],
            tenant_slug=cfg["tenant_slug"] or None,
            custom_fields=cf,
        )
        netbox_device = created
        attributes[ATTR_NETBOX_DEVICE_ID] = str(created["id"])
        attributes[ATTR_NETBOX_URL] = _device_web_url(cfg["base_url"], created)
        attributes[ATTR_NETBOX_LINK] = link
    netbox_device_id = int(netbox_device["id"])

    # Resolve the prefix to draw from.
    effective_prefix = prefix or attributes.get("network_subnet")
    if address is None:
        if not effective_prefix:
            return NetboxAssignIpResult(
                ok=False,
                message="Provide a prefix or set the device's local subnet first.",
            )
        prefix_obj = await nb.find_prefix(effective_prefix)
        if prefix_obj is None:
            return NetboxAssignIpResult(
                ok=False, message=f"NetBox has no prefix matching {effective_prefix}."
            )
        available = await nb.available_ips(int(prefix_obj["id"]))
        if not available:
            return NetboxAssignIpResult(
                ok=False, message=f"No available IPs left in {effective_prefix}."
            )
        address = available[0]["address"]

    ip = await nb.create_ip(
        address=address,
        device_id=netbox_device_id,
        custom_fields=cf,
        description=description,
    )
    # Local view uses the bare address (no mask).
    bare = address.split("/")[0]
    attributes["network_ip"] = bare
    attributes[ATTR_NETBOX_IP_ID] = int(ip["id"])
    attributes[ATTR_NETBOX_SYNC_STATUS] = "ok"
    device.attributes = attributes
    await db.commit()

    await publish_job_event(
        job_id,
        "graph.device.netbox",
        {
            "device_id": str(device.id),
            "job_id": str(job_id),
            "status": "ok",
            "ip": bare,
            "netbox_url": attributes.get(ATTR_NETBOX_URL),
            "netbox_device_id": attributes.get(ATTR_NETBOX_DEVICE_ID),
        },
    )
    return NetboxAssignIpResult(ok=True, ip=bare, netbox_ip_id=int(ip["id"]), message="Assigned.")


async def handle_webhook(db, payload: dict) -> dict:
    """Process an inbound NetBox webhook and flag conflicts in Stagewire.

    NetBox sends ``{event, model, data, snapshots}``. We care about ``ip_address``
    objects (the link between a Stagewire device and its IP). When an IP is
    deleted or reassigned away from the device we tagged, we mark the local
    device as a conflict and push a realtime banner; when the address simply
    changes we adopt the new value (NetBox remains the IPAM source of truth).
    """
    model = (payload.get("model") or "").replace("_", "")
    event = payload.get("event") or ""
    if model != "ipaddress" or event not in ("updated", "deleted"):
        return {"handled": False, "reason": "ignored"}

    data = payload.get("data") or {}
    pre = (payload.get("snapshots") or {}).get("pre") or {}
    cf = data.get("custom_fields") or pre.get("custom_fields") or {}
    stagewire_device_id = cf.get(NETBOX_CF_DEVICE_ID)
    if not stagewire_device_id:
        return {"handled": False, "reason": "no_stagewire_link"}

    result = await db.execute(
        select(GraphDevice).where(GraphDevice.id == uuid.UUID(stagewire_device_id))
    )
    device = result.scalar_one_or_none()
    if device is None:
        return {"handled": False, "reason": "device_not_found"}

    attributes = dict(device.attributes or {})
    job_id = device.job_id
    if event == "deleted":
        attributes[ATTR_NETBOX_SYNC_STATUS] = "conflict"
        attributes[ATTR_NETBOX_IP_ID] = None
        message = "The IP was deleted in NetBox."
    else:
        assigned_id = data.get("assigned_object_id")
        netbox_device_id = attributes.get(ATTR_NETBOX_DEVICE_ID)
        if assigned_id is None or str(assigned_id) != str(netbox_device_id):
            attributes[ATTR_NETBOX_SYNC_STATUS] = "conflict"
            message = "The IP was reassigned to another NetBox object."
        else:
            address = data.get("address", "")
            attributes["network_ip"] = address.split("/")[0]
            attributes[ATTR_NETBOX_SYNC_STATUS] = "ok"
            message = "IP updated from NetBox."

    device.attributes = attributes
    await db.commit()

    if job_id is not None:
        await publish_job_event(
            job_id,
            "graph.device.netbox",
            {
                "device_id": str(device.id),
                "job_id": str(job_id),
                "status": attributes.get(ATTR_NETBOX_SYNC_STATUS),
                "ip": attributes.get("network_ip"),
                "message": message,
            },
        )
    return {
        "handled": True,
        "device_id": str(device.id),
        "status": attributes.get(ATTR_NETBOX_SYNC_STATUS),
    }
