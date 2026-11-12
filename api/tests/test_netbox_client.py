import hashlib
import hmac
import json

import httpx
import pytest

from app.domains.netbox.client import NetboxClient
from app.domains.netbox.webhook import verify_netbox_signature


def _fake_netbox_handler(request: httpx.Request) -> httpx.Response:
    """Stateful in-memory NetBox fake so idempotent creates are observable."""
    state = _fake_netbox_handler.state  # type: ignore[attr-defined]
    path = request.url.path
    method = request.method
    params = request.url.params

    if method == "GET":
        if path == "/api/extras/custom-fields/":
            # NetBox 4.7 returns every custom field (it ignores the `key` query param)
            # and identifies fields by `name` (not `key`). The client matches by name.
            all_cf = list(state["cf"].values())
            return httpx.Response(
                200,
                json={
                    "count": len(all_cf),
                    "next": None,
                    "results": all_cf,
                },
            )
        if path == "/api/extras/webhooks/":
            name = params.get("name")
            existing = state["webhooks"].get(name) if name else None
            return httpx.Response(
                200,
                json={
                    "count": 1 if existing else 0,
                    "next": None,
                    "results": [existing] if existing else [],
                },
            )
        if path == "/api/dcim/device-roles/":
            slug = params.get("slug")
            existing = state["roles"].get(slug) if slug else None
            return httpx.Response(
                200,
                json={
                    "count": 1 if existing else 0,
                    "next": None,
                    "results": [existing] if existing else [],
                },
            )
        if path == "/api/dcim/manufacturers/":
            slug = params.get("slug")
            existing = state["mans"].get(slug) if slug else None
            return httpx.Response(
                200,
                json={
                    "count": 1 if existing else 0,
                    "next": None,
                    "results": [existing] if existing else [],
                },
            )
        if path == "/api/dcim/device-types/":
            existing = state["types"].get("type")
            return httpx.Response(
                200,
                json={
                    "count": 1 if existing else 0,
                    "next": None,
                    "results": [existing] if existing else [],
                },
            )
        if path == "/api/dcim/devices/":
            return httpx.Response(200, json={"count": 0, "next": None, "results": []})
        if path == "/api/ipam/vlans/":
            return httpx.Response(
                200,
                json={
                    "count": 1,
                    "next": None,
                    "results": [{"id": 1, "vid": 100, "name": "Mgmt", "slug": "mgmt"}],
                },
            )
        if path == "/api/ipam/prefixes/":
            # One prefix sitting in VLAN 1; the vlan_id filter is honoured
            # trivially (the fake only has this single row).
            return httpx.Response(
                200,
                json={
                    "count": 1,
                    "next": None,
                    "results": [
                        {
                            "id": 5,
                            "prefix": "10.0.0.0/24",
                            "vlan": {"id": 1, "vid": 100},
                            "site": {"slug": "hq"},
                            "tenant": {"slug": "stagewire"},
                            "description": "Mgmt subnet",
                        }
                    ],
                },
            )
        if path == "/api/ipam/prefixes/5/available-ips/":
            return httpx.Response(200, json=[{"address": "10.0.0.5/24", "family": 4}])

    if method == "PATCH":
        body = json.loads(request.content or b"{}")
        if path.startswith("/api/extras/custom-fields/") and path.endswith("/"):
            cf_id = int(path.split("/")[-2])
            # The fake stores custom fields by key; find the row by id to patch it.
            for _key, row in state["cf"].items():
                if row.get("id") == cf_id:
                    row.update(body)
                    return httpx.Response(200, json=row)
            return httpx.Response(404, json={"detail": "not found"})

    if method == "POST":
        body = json.loads(request.content or b"{}")
        if path == "/api/extras/custom-fields/":
            state["cf"][body.get("name")] = {**body, "id": len(state["cf"]) + 1}
            return httpx.Response(201, json=state["cf"][body.get("name")])
        if path == "/api/extras/webhooks/":
            state["webhooks"][body.get("name")] = body
            return httpx.Response(201, json={**body, "id": len(state["webhooks"])})
        if path == "/api/dcim/device-roles/":
            state["roles"][body.get("slug")] = body
            return httpx.Response(201, json={**body, "id": 10})
        if path == "/api/dcim/manufacturers/":
            state["mans"][body.get("slug")] = body
            return httpx.Response(201, json={**body, "id": 20})
        if path == "/api/dcim/device-types/":
            state["types"]["type"] = body
            return httpx.Response(201, json={**body, "id": 30})
        if path == "/api/dcim/devices/":
            return httpx.Response(
                201,
                json={
                    "id": 100,
                    "url": "http://netbox/api/dcim/devices/100/",
                    "display": {"url": "/dcim/devices/100/"},
                },
            )
        if path == "/api/ipam/ip-addresses/":
            return httpx.Response(201, json={"id": 200, "address": body.get("address")})

    if method == "PATCH" and path == "/api/dcim/devices/100/":
        return httpx.Response(200, json={"id": 100})
    if method == "DELETE" and path == "/api/ipam/ip-addresses/200/":
        return httpx.Response(204)

    return httpx.Response(404, json={"detail": f"unhandled {method} {path}"})


_fake_netbox_handler.state = {  # type: ignore[attr-defined]
    "cf": {},
    "webhooks": {},
    "roles": {},
    "mans": {},
    "types": {},
}


@pytest.fixture
def client() -> NetboxClient:
    transport = httpx.MockTransport(_fake_netbox_handler)
    return NetboxClient(base_url="http://netbox", token="test-token", transport=transport)


async def test_ensure_custom_fields_idempotent(client: NetboxClient) -> None:
    # Four historical fields plus stagewire_venue_id (added for venue base-rig sync).
    created = await client.ensure_custom_fields()
    assert len(created) == 5
    assert "stagewire_venue_id" in created
    # Second pass finds them already present (fake returns all, so still 0 new).
    again = await client.ensure_custom_fields()
    assert again == []


async def test_ensure_custom_fields_heals_missing_object_types(client: NetboxClient) -> None:
    # Reset shared fake state so the PATCH-by-id lookup is unambiguous across tests.
    _fake_netbox_handler.state["cf"] = {}  # type: ignore[attr-defined]
    # Simulate a field left stale by an older build: it exists (by key) but has no
    # object_types, so it is "not valid for this object type" when set on a device.
    _fake_netbox_handler.state["cf"]["stagewire_device_id"] = {  # type: ignore[attr-defined]
        "id": 1,
        "key": "stagewire_device_id",
        "object_types": [],
    }
    healed = await client.ensure_custom_fields()
    assert "stagewire_device_id" in healed
    patched = _fake_netbox_handler.state["cf"]["stagewire_device_id"]  # type: ignore[attr-defined]
    assert "dcim.device" in patched["object_types"]
    assert "ipam.ipaddress" in patched["object_types"]


async def test_ensure_webhook_creates_once(client: NetboxClient) -> None:
    first = await client.ensure_webhook("stagewire-sync", "http://cb", "secret")
    assert first is True
    second = await client.ensure_webhook("stagewire-sync", "http://cb", "secret")
    assert second is False


async def test_ensure_device_type_creates_manufacturer_and_type(client: NetboxClient) -> None:
    type_id = await client.ensure_device_type("Stagewire Device", "Generic")
    assert isinstance(type_id, int)


async def test_create_and_find_device(client: NetboxClient) -> None:
    device = await client.create_device(
        name="Main Mixer",
        site_slug="stage-dev",
        device_type_id=30,
        role_slug="stagewire",
        status_slug="staged",
        tenant_slug=None,
        custom_fields={"stagewire_device_id": "abc"},
    )
    assert device["id"] == 100
    found = await client.find_device("abc")
    assert found is None  # fake returns empty list, mirrors idempotency probe


async def test_ipam_flow(client: NetboxClient) -> None:
    prefix = await client.find_prefix("10.0.0.0/24")
    assert prefix["id"] == 5
    ips = await client.available_ips(5)
    assert ips[0]["address"] == "10.0.0.5/24"
    created = await client.create_ip(
        address="10.0.0.5/24", device_id=100, custom_fields={"stagewire_device_id": "abc"}
    )
    assert created["id"] == 200


async def test_list_vlans_parses_response(client: NetboxClient) -> None:
    vlans = await client.list_vlans()
    assert len(vlans) == 1
    assert vlans[0]["id"] == 1
    assert vlans[0]["vid"] == 100
    assert vlans[0]["name"] == "Mgmt"


async def test_list_prefixes_parses_nested_vlan_and_scope(client: NetboxClient) -> None:
    prefixes = await client.list_prefixes(vlan_id=1)
    assert len(prefixes) == 1
    p = prefixes[0]
    assert p["id"] == 5
    assert p["prefix"] == "10.0.0.0/24"
    assert p["vlan_id"] == 1
    assert p["site_slug"] == "hq"
    assert p["tenant_slug"] == "stagewire"
    assert p["description"] == "Mgmt subnet"


def test_webhook_signature_valid_and_invalid() -> None:
    secret = "super-secret"
    body = b'{"event":"updated","model":"ip_address"}'
    sig = hmac.new(secret.encode(), body, hashlib.sha512).hexdigest()
    assert verify_netbox_signature(secret, body, sig) is True
    assert verify_netbox_signature(secret, body, "deadbeef") is False
    assert verify_netbox_signature(secret, body, None) is False
    # SHA-256 fallback is also accepted.
    sig256 = hmac.new(secret.encode(), body, hashlib.sha256).hexdigest()
    assert verify_netbox_signature(secret, body, sig256) is True
