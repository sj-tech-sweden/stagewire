import hashlib
import hmac
import json
import uuid
from unittest.mock import AsyncMock

from httpx import ASGITransport, AsyncClient
from sqlalchemy import select

from app.core import db as db_mod
from app.domains.audio.models import ProductionJob
from app.domains.graph.models import GraphDevice
from app.domains.netbox import config as netbox_config
from app.domains.netbox.schemas import NetboxAssignIpResult, NetboxProvisionResult
from app.main import app

BASE = "/api/v1"


async def _seed_job_and_device() -> tuple[str, str]:
    async with db_mod.SessionLocal() as db:
        job = ProductionJob(title="Test Job")
        db.add(job)
        await db.commit()
        await db.refresh(job)
        device = GraphDevice(
            id=uuid.uuid4(),
            name="Mixer",
            domain="audio",
            kind="mixer",
            job_id=job.id,
            attributes={},
        )
        db.add(device)
        await db.commit()
        return str(job.id), str(device.id)


async def test_netbox_config_default_and_update(auth_headers) -> None:
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.get(f"{BASE}/netbox", headers=auth_headers)
        assert resp.status_code == 200
        assert resp.json()["enabled"] is False

        resp = await client.put(
            f"{BASE}/netbox",
            headers=auth_headers,
            json={
                "enabled": True,
                "base_url": "http://netbox",
                "api_token": "tok",
                "site_slug": "stage-dev",
                "public_url": "http://stagewire",
            },
        )
        assert resp.status_code == 200
        body = resp.json()
        assert body["enabled"] is True
        assert body["has_api_token"] is True


async def test_netbox_provision_routes_to_service(auth_headers, monkeypatch) -> None:
    from app.domains.netbox import service as nb_service

    fake = AsyncMock(
        return_value=NetboxProvisionResult(
            ok=True, code="provisioned", message="ok", created=["webhook"]
        )
    )
    monkeypatch.setattr(nb_service, "provision", fake)

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.post(f"{BASE}/netbox/provision", headers=auth_headers)
        assert resp.status_code == 200
        assert resp.json()["created"] == ["webhook"]
        assert fake.await_count == 1


async def test_netbox_assign_ip_routes_to_service(auth_headers, monkeypatch) -> None:
    from app.domains.netbox import service as nb_service

    _, device_id = await _seed_job_and_device()
    fake = AsyncMock(
        return_value=NetboxAssignIpResult(ok=True, ip="10.0.0.5", netbox_ip_id=200, message="ok")
    )
    monkeypatch.setattr(nb_service, "assign_ip", fake)

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.post(
            f"{BASE}/netbox/assign-ip",
            headers=auth_headers,
            json={"device_id": device_id, "prefix": "10.0.0.0/24"},
        )
        assert resp.status_code == 200
        assert resp.json()["ip"] == "10.0.0.5"
        fake.assert_awaited_once()


async def test_netbox_list_vlans_and_prefixes(auth_headers, monkeypatch) -> None:
    from app.domains.netbox import service as nb_service
    from app.domains.netbox.client import NetboxClient

    fake_client = AsyncMock(spec=NetboxClient)
    fake_client.list_vlans = AsyncMock(
        return_value=[{"id": 1, "vid": 100, "name": "Mgmt", "slug": "mgmt"}]
    )
    fake_client.list_prefixes = AsyncMock(
        return_value=[
            {
                "id": 5,
                "prefix": "10.0.0.0/24",
                "vlan_id": 1,
                "site_slug": "hq",
                "tenant_slug": "stagewire",
                "description": "Mgmt subnet",
            }
        ]
    )
    monkeypatch.setattr(nb_service, "get_client", AsyncMock(return_value=fake_client))

    # Configure a tenant/site so we also confirm they are forwarded to the client.
    async with db_mod.SessionLocal() as db:
        await netbox_config.save_integration_config(
            db,
            enabled=True,
            base_url="http://netbox",
            api_token="tok",
            tenant_slug="stagewire",
            site_slug="hq",
        )

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.get(f"{BASE}/netbox/vlans", headers=auth_headers)
        assert resp.status_code == 200
        assert resp.json()[0]["vid"] == 100

        resp = await client.get(
            f"{BASE}/netbox/prefixes", headers=auth_headers, params={"vlan_id": 1}
        )
        assert resp.status_code == 200
        body = resp.json()
        assert body[0]["prefix"] == "10.0.0.0/24"

    # The configured tenant/site scope is forwarded to the client.
    _, kwargs = fake_client.list_prefixes.call_args
    assert kwargs["tenant_slug"] == "stagewire"
    assert kwargs["site_slug"] == "hq"
    assert kwargs["vlan_id"] == 1


async def _seed_device(attributes: dict) -> str:
    async with db_mod.SessionLocal() as db:
        await netbox_config.save_webhook_secret(db, "secret")
        device = GraphDevice(
            id=uuid.uuid4(),
            name="Mixer",
            domain="audio",
            kind="mixer",
            attributes=attributes,
        )
        db.add(device)
        await db.commit()
        return str(device.id)


async def test_netbox_webhook_rejects_bad_signature() -> None:
    raw = json.dumps({"event": "updated", "model": "ip_address"}).encode()
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.post(
            f"{BASE}/netbox/webhook",
            content=raw,
            headers={"X-Hook-Signature": "nope", "Content-Type": "application/json"},
        )
        assert resp.status_code == 401


async def test_netbox_webhook_conflict_on_reassign() -> None:
    dev_id = await _seed_device({"netbox_device_id": "100"})
    payload = {
        "event": "updated",
        "model": "ip_address",
        "data": {
            "id": 1,
            "address": "10.0.0.9/24",
            "assigned_object_id": 999,  # != 100 → reassigned away
            "custom_fields": {"stagewire_device_id": dev_id},
        },
    }
    raw = json.dumps(payload).encode()
    sig = hmac.new(b"secret", raw, hashlib.sha512).hexdigest()

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.post(
            f"{BASE}/netbox/webhook",
            content=raw,
            headers={"X-Hook-Signature": sig, "Content-Type": "application/json"},
        )
        assert resp.status_code == 200
        assert resp.json()["handled"] is True
        assert resp.json()["status"] == "conflict"

    async with db_mod.SessionLocal() as db:
        dev = (
            await db.execute(select(GraphDevice).where(GraphDevice.id == uuid.UUID(dev_id)))
        ).scalar_one()
        assert dev.attributes["netbox_sync_status"] == "conflict"


async def test_netbox_webhook_accepts_address_update() -> None:
    dev_id = await _seed_device({"netbox_device_id": "100"})
    payload = {
        "event": "updated",
        "model": "ip_address",
        "data": {
            "id": 1,
            "address": "10.0.0.9/24",
            "assigned_object_id": 100,  # matches → adopt new value
            "custom_fields": {"stagewire_device_id": dev_id},
        },
    }
    raw = json.dumps(payload).encode()
    sig = hmac.new(b"secret", raw, hashlib.sha512).hexdigest()

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.post(
            f"{BASE}/netbox/webhook",
            content=raw,
            headers={"X-Hook-Signature": sig, "Content-Type": "application/json"},
        )
        assert resp.status_code == 200
        assert resp.json()["status"] == "ok"

    async with db_mod.SessionLocal() as db:
        dev = (
            await db.execute(select(GraphDevice).where(GraphDevice.id == uuid.UUID(dev_id)))
        ).scalar_one()
        assert dev.attributes["network_ip"] == "10.0.0.9"
        assert dev.attributes["netbox_sync_status"] == "ok"
