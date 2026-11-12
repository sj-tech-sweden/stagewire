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
from app.domains.netbox import service as netbox_service
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


async def _seed_venue_and_device() -> tuple[str, str]:
    from app.domains.venues.models import Venue

    async with db_mod.SessionLocal() as db:
        venue = Venue(name="Venue Sync Test")
        db.add(venue)
        await db.commit()
        await db.refresh(venue)
        device = GraphDevice(
            id=uuid.uuid4(),
            name="Venue Mixer",
            domain="audio",
            kind="mixer",
            # A base-rig device belongs to the venue and to no job (job_id IS NULL),
            # which is exactly the scope sync_venue mirrors.
            venue_id=venue.id,
            job_id=None,
            attributes={},
        )
        db.add(device)
        await db.commit()
        return str(venue.id), str(device.id)


def test_device_web_url_uses_id_not_display() -> None:
    # NetBox 4.7 returns `display` as a plain string (older versions returned a
    # dict with a `url` key). Building the UI URL from `display.get("url")` raised
    # AttributeError and turned a successful sync into a 500. The URL must come
    # from the device id, which is stable across versions.
    base = "http://netbox:8088"
    as_string = {"id": 7, "display": "FOH Mixer 1", "url": "http://netbox:8088/api/dcim/devices/7/"}
    as_dict = {
        "id": 7,
        "display": {"url": "/dcim/devices/7/"},
        "url": "http://netbox:8088/api/dcim/devices/7/",
    }
    for device in (as_string, as_dict):
        assert netbox_service._device_web_url(base, device) == "http://netbox:8088/dcim/devices/7/"
    # Missing id falls back to the raw url/api url without crashing.
    assert (
        netbox_service._device_web_url(base, {"url": "http://x/api/dcim/devices/9/"})
        == "http://x/api/dcim/devices/9/"
    )


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


async def test_netbox_assign_ip_venue_scoped(auth_headers, monkeypatch) -> None:
    """assign_ip works for a venue base-rig device: the NetBox object + link carry
    stagewire_venue_id (not job_id) and the realtime event goes to the venue room.
    """
    from app.domains.netbox import service as nb_service
    from app.domains.netbox.client import NetboxClient

    venue_id, device_id = await _seed_venue_and_device()
    async with db_mod.SessionLocal() as db:
        await netbox_config.save_integration_config(
            db,
            enabled=True,
            base_url="http://netbox",
            api_token="tok",
            site_slug="hq",
            device_role_slug="stagewire",
            device_type_id=1,
            public_url="http://stagewire",
        )

    # A venue-synced device already exists in NetBox, so assign_ip should find it
    # (no create) and draw an available IP from the given prefix.
    fake_client = AsyncMock(spec=NetboxClient)
    fake_client.find_device = AsyncMock(
        return_value={
            "id": 7,
            "custom_fields": {
                "stagewire_device_id": device_id,
                "stagewire_venue_id": venue_id,
            },
        }
    )
    fake_client.find_prefix = AsyncMock(return_value={"id": 5})
    fake_client.available_ips = AsyncMock(return_value=[{"address": "10.0.0.9/24"}])
    fake_client.create_ip = AsyncMock(return_value={"id": 22})
    monkeypatch.setattr(nb_service, "get_client", AsyncMock(return_value=fake_client))

    captured: dict = {}

    async def _capture_venue(venue_id_arg, event_type, payload):
        captured["venue_id"] = venue_id_arg
        captured["event_type"] = event_type
        captured["payload"] = payload

    monkeypatch.setattr(nb_service, "publish_venue_event", _capture_venue)
    # Ensure the job path is NOT taken for a venue device.
    monkeypatch.setattr(nb_service, "publish_job_event", AsyncMock())

    async with db_mod.SessionLocal() as db:
        result = await nb_service.assign_ip(
            db, venue_id=uuid.UUID(venue_id), device_id=uuid.UUID(device_id), prefix="10.0.0.0/24"
        )
        assert result.ok is True
        assert result.ip == "10.0.0.9"

        # The local device records the assigned IP and ok status.
        dev = (
            await db.execute(select(GraphDevice).where(GraphDevice.id == uuid.UUID(device_id)))
        ).scalar_one()
        assert dev.attributes["network_ip"] == "10.0.0.9"
        assert dev.attributes["netbox_sync_status"] == "ok"

    # Realtime broadcast targeted the venue room, not a job room.
    assert captured["venue_id"] == uuid.UUID(venue_id)
    assert captured["event_type"] == "graph.device.netbox"
    assert captured["payload"]["venue_id"] == venue_id
    # The NetBox link built for this device points at the venue view, not a job.
    fake_client.find_device.assert_awaited()


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


async def test_netbox_sync_job_missing_config_returns_200_not_500(auth_headers) -> None:
    # A missing site/role/device-type used to blow up as a 500 (NetBox 400 from an
    # empty {"slug": ""} FK bubbled up). sync_job must validate and answer 200/ok=False.
    job_id, _ = await _seed_job_and_device()
    async with db_mod.SessionLocal() as db:
        await netbox_config.save_integration_config(
            db,
            enabled=True,
            base_url="http://netbox",
            api_token="tok",
            site_slug="",
            device_role_slug="",
            device_type_id=None,
        )

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.post(f"{BASE}/netbox/sync-job/{job_id}", headers=auth_headers)
        assert resp.status_code == 200
        body = resp.json()
        assert body["ok"] is False
        assert "site" in body["message"].lower() or "device type" in body["message"].lower()


async def test_netbox_sync_venue_missing_config_returns_200_not_500(auth_headers) -> None:
    # Mirror of the job test: a missing site/role/device-type must yield a clean
    # 200/ok=False, never a 500, for the venue base-rig sync endpoint too.
    venue_id, _ = await _seed_venue_and_device()
    async with db_mod.SessionLocal() as db:
        await netbox_config.save_integration_config(
            db,
            enabled=True,
            base_url="http://netbox",
            api_token="tok",
            site_slug="",
            device_role_slug="",
            device_type_id=None,
        )

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.post(f"{BASE}/netbox/sync-venue/{venue_id}", headers=auth_headers)
        assert resp.status_code == 200
        body = resp.json()
        assert body["ok"] is False
        assert "site" in body["message"].lower() or "device type" in body["message"].lower()


async def test_netbox_sync_venue_mirrors_base_rig_with_venue_cf(auth_headers, monkeypatch) -> None:
    """The venue base rig mirrors into NetBox carrying stagewire_venue_id (not job_id).

    Uses an in-memory NetBox fake so we can assert the exact custom fields written,
    confirming venue sync is scoped correctly and link back to the venue, not a job.
    """
    from httpx import MockTransport, Request, Response

    from app.domains.netbox.client import NetboxClient

    venue_id, device_id = await _seed_venue_and_device()
    async with db_mod.SessionLocal() as db:
        await netbox_config.save_integration_config(
            db,
            enabled=True,
            base_url="http://netbox",
            api_token="tok",
            site_slug="hq",
            device_role_slug="stagewire",
            device_type_id=1,
            public_url="http://stagewire",
        )

    state: dict = {"cf": {}, "devices": {}, "next_device_id": 1}

    def handler(request: Request) -> Response:
        path = request.url.path
        method = request.method
        params = request.url.params
        if method == "GET" and path == "/api/extras/custom-fields/":
            all_cf = list(state["cf"].values())
            return Response(200, json={"count": len(all_cf), "next": None, "results": all_cf})
        if method == "POST" and path == "/api/extras/custom-fields/":
            body = json.loads(request.content or b"{}")
            cf_id = len(state["cf"]) + 1
            row = {**body, "id": cf_id, "object_types": body.get("object_types", [])}
            state["cf"][body["name"]] = row
            return Response(201, json=row)
        if (
            method == "PATCH"
            and path.startswith("/api/extras/custom-fields/")
            and path.endswith("/")
        ):
            cf_id = int(path.split("/")[-2])
            body = json.loads(request.content or b"{}")
            for row in state["cf"].values():
                if row.get("id") == cf_id:
                    row.update(body)
                    return Response(200, json=row)
            return Response(404, json={})
        if method == "GET" and path == "/api/dcim/devices/":
            key = params.get("cf_stagewire_device_id")
            matches = [
                d
                for d in state["devices"].values()
                if d.get("custom_fields", {}).get("stagewire_device_id") == key
            ]
            return Response(200, json={"count": len(matches), "next": None, "results": matches})
        if method == "POST" and path == "/api/dcim/devices/":
            body = json.loads(request.content or b"{}")
            did = state["next_device_id"]
            state["next_device_id"] += 1
            row = {**body, "id": did}
            state["devices"][str(did)] = row
            return Response(201, json=row)
        return Response(404, json={})

    fake = NetboxClient(base_url="http://netbox", token="tok", transport=MockTransport(handler))

    # service.sync_venue builds the client via get_client; swap it for the fake.
    async def _fake_get_client(db):
        return fake

    monkeypatch.setattr(netbox_service, "get_client", _fake_get_client)

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.post(f"{BASE}/netbox/sync-venue/{venue_id}", headers=auth_headers)
        assert resp.status_code == 200
        body = resp.json()
        assert body["ok"] is True
        assert body["devices_created"] == 1

    # The mirrored NetBox device carries the venue id, never a job id.
    assert state["devices"], "no device was created in the fake NetBox"
    mirrored = next(iter(state["devices"].values()))
    cf = mirrored["custom_fields"]
    assert cf["stagewire_venue_id"] == venue_id
    assert "stagewire_job_id" not in cf
    assert cf["stagewire_device_id"] == device_id

    # The local base-rig device records the NetBox id + ok status.
    async with db_mod.SessionLocal() as db:
        dev = (
            await db.execute(select(GraphDevice).where(GraphDevice.id == uuid.UUID(device_id)))
        ).scalar_one()
        assert dev.attributes["netbox_sync_status"] == "ok"
        assert dev.attributes["netbox_device_id"] == str(mirrored["id"])


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
