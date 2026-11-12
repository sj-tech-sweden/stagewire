"""Binding a physical Stockwire inventory asset to a Stagewire device.

The canonical inventory ID lives in ``stockwire_device_id``; raw scanned/typed codes and
descriptive identifiers live in ``stockwire_asset_*`` attributes. The raw code is always kept so
the crew view can look devices up by the value a user actually scans.
"""

from unittest.mock import AsyncMock, patch

from httpx import ASGITransport, AsyncClient

from app.main import app

BASE = "/api/v1"


async def _make_job_and_device(client, headers):
    job = await client.post(f"{BASE}/jobs", json={"title": "Bind E2E"}, headers=headers)
    job_id = job.json()["id"]
    dev = await client.post(
        f"{BASE}/jobs/{job_id}/graph/devices",
        json={"domain": "audio", "name": "Stagebox A", "kind": "stagebox"},
        headers=headers,
    )
    return job_id, dev.json()["id"]


async def test_bind_asset_records_code_locally(auth_headers):
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        job_id, device_id = await _make_job_and_device(client, auth_headers)

        # Without the Stockwire integration, the raw code is kept without claiming a canonical ID.
        bound = await client.post(
            f"{BASE}/jobs/{job_id}/graph/devices/{device_id}/bind-asset",
            json={
                "code": "ASSET-999",
                "tag": "TAG-999",
                "serial": "SN-999",
                "expected_revision": 1,
            },
            headers=auth_headers,
        )
        assert bound.status_code == 200, bound.text
        attrs = bound.json()["attributes"]
        assert attrs.get("stockwire_asset_id") is None
        assert attrs["stockwire_asset_code"] == "ASSET-999"
        assert attrs["stockwire_asset_tag"] == "TAG-999"
        assert attrs["stockwire_asset_serial"] == "SN-999"
        assert bound.json()["stockwire_device_id"] is None

        # The device read from the graph reflects the binding.
        graph = (await client.get(f"{BASE}/jobs/{job_id}/graph", headers=auth_headers)).json()
        device = next(d for d in graph["devices"] if d["id"] == device_id)
        assert device["attributes"].get("stockwire_asset_id") is None
        assert device["attributes"]["stockwire_asset_code"] == "ASSET-999"


async def test_rebinding_removes_the_legacy_asset_id_attribute(auth_headers):
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        job_id, device_id = await _make_job_and_device(client, auth_headers)
        legacy = await client.patch(
            f"{BASE}/jobs/{job_id}/graph/devices/{device_id}",
            json={
                "attributes": {
                    "stockwire_asset_id": "OLD-ID",
                    "stockwire_asset_code": "OLD-CODE",
                },
                "expected_revision": 1,
            },
            headers=auth_headers,
        )
        assert legacy.status_code == 200, legacy.text

        rebound = await client.post(
            f"{BASE}/jobs/{job_id}/graph/devices/{device_id}/bind-asset",
            json={"code": "NEW-CODE", "expected_revision": legacy.json()["revision"]},
            headers=auth_headers,
        )
        assert rebound.status_code == 200, rebound.text
        assert rebound.json()["attributes"].get("stockwire_asset_id") is None
        assert rebound.json()["attributes"]["stockwire_asset_code"] == "NEW-CODE"


async def test_authenticated_unbind_clears_all_asset_identifiers(auth_headers):
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        job = await client.post(
            f"{BASE}/jobs", json={"title": "Unbind asset"}, headers=auth_headers
        )
        job_id = job.json()["id"]
        device = await client.post(
            f"{BASE}/jobs/{job_id}/graph/devices",
            json={
                "domain": "audio",
                "name": "Bound stagebox",
                "kind": "stagebox",
                "stockwire_device_id": "ASSET-1",
                "attributes": {
                    "stockwire_asset_id": "ASSET-1",
                    "stockwire_asset_code": "TAG-1",
                    "stockwire_asset_tag": "TAG-1",
                    "stockwire_asset_serial": "SN-1",
                    "stockwire_asset_barcode": "BAR-1",
                    "stockwire_asset_qr_code": "QR-1",
                    "stockwire_asset_rfid": "RFID-1",
                    "stockwire_asset_description": "Bound device",
                },
            },
            headers=auth_headers,
        )

        unbound = await client.delete(
            f"{BASE}/jobs/{job_id}/graph/devices/{device.json()['id']}/asset-binding",
            params={"expected_revision": device.json()["revision"]},
            headers=auth_headers,
        )
        assert unbound.status_code == 200, unbound.text
        assert unbound.json()["stockwire_device_id"] is None
        assert all(
            unbound.json()["attributes"][key] is None
            for key in (
                "stockwire_asset_id",
                "stockwire_asset_code",
                "stockwire_asset_tag",
                "stockwire_asset_serial",
                "stockwire_asset_barcode",
                "stockwire_asset_qr_code",
                "stockwire_asset_rfid",
                "stockwire_asset_description",
            )
        )


async def test_bind_asset_requires_job_scope(auth_headers):
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        job_id, device_id = await _make_job_and_device(client, auth_headers)
        # A device from a different (nonexistent) job must 404, not bind cross-job.
        other = await client.post(
            f"{BASE}/jobs/00000000-0000-0000-0000-000000000000/graph/devices/{device_id}/bind-asset",
            json={"code": "X", "expected_revision": 1},
            headers=auth_headers,
        )
        assert other.status_code == 404


async def test_asset_binding_rejects_virtual_graph_nodes(auth_headers):
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        job_id = (
            await client.post(
                f"{BASE}/jobs", json={"title": "Virtual target"}, headers=auth_headers
            )
        ).json()["id"]
        channel = await client.post(
            f"{BASE}/jobs/{job_id}/graph/devices",
            json={"domain": "audio", "name": "Channel 1", "kind": "channel"},
            headers=auth_headers,
        )
        channel_id = channel.json()["id"]

        bind = await client.post(
            f"{BASE}/jobs/{job_id}/graph/devices/{channel_id}/bind-asset",
            json={"code": "ASSET-1", "expected_revision": 1},
            headers=auth_headers,
        )
        assert bind.status_code == 422
        assert "physical gear" in bind.json()["detail"]

        patch_asset_id = await client.patch(
            f"{BASE}/jobs/{job_id}/graph/devices/{channel_id}",
            json={"stockwire_device_id": "ASSET-1", "expected_revision": 1},
            headers=auth_headers,
        )
        assert patch_asset_id.status_code == 422
        assert "physical gear" in patch_asset_id.json()["detail"]

        patch_asset_attributes = await client.patch(
            f"{BASE}/jobs/{job_id}/graph/devices/{channel_id}",
            json={
                "attributes": {"stockwire_asset_code": "ASSET-1"},
                "expected_revision": 1,
            },
            headers=auth_headers,
        )
        assert patch_asset_attributes.status_code == 422
        assert "physical gear" in patch_asset_attributes.json()["detail"]


async def test_bind_keeps_raw_code_separate_from_canonical_id(auth_headers):
    """Resolved IDs use the top-level field while the scanned code remains available to crews."""
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        job_id, device_id = await _make_job_and_device(client, auth_headers)
        resolved = {
            "asset_id": "42",
            "asset_tag": "TAG-42",
            "serial_number": "SN-42",
            "barcode": "1100521",
            "qr_code": "TAG-42",
            "rfid": "RFID-42",
            "description": "A resolved unit",
        }
        with (
            patch(
                "app.domains.graph.router.load_integration_config",
                return_value={"enabled": True, "base_url": "http://stockwire", "api_key": "k"},
            ),
            patch("app.domains.graph.router.StockwireClient") as MockClient,
        ):
            MockClient.return_value.resolve_asset = AsyncMock(return_value=resolved)
            bound = await client.post(
                f"{BASE}/jobs/{job_id}/graph/devices/{device_id}/bind-asset",
                json={"code": "ASSET-RAW", "expected_revision": 1},
                headers=auth_headers,
            )
        assert bound.status_code == 200, bound.text
        attrs = bound.json()["attributes"]
        assert attrs["stockwire_asset_code"] == "ASSET-RAW"  # raw scanned value
        assert attrs.get("stockwire_asset_id") is None
        assert bound.json()["stockwire_device_id"] == "42"
        assert attrs["stockwire_asset_tag"] == "TAG-42"
        assert attrs["stockwire_asset_barcode"] == "1100521"
        assert attrs["stockwire_asset_qr_code"] == "TAG-42"
        assert attrs["stockwire_asset_rfid"] == "RFID-42"
        assert bound.json()["stockwire_device_id"] == "42"


async def test_picker_binding_resolves_canonical_asset_id_and_keeps_scan_tag(auth_headers):
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        job_id, device_id = await _make_job_and_device(client, auth_headers)
        resolved = {
            "asset_id": "42",
            "asset_tag": "TAG-42",
            "serial_number": "SN-42",
            "description": "A selected unit",
        }
        with (
            patch(
                "app.domains.graph.router.load_integration_config",
                return_value={"enabled": True, "base_url": "http://stockwire", "api_key": "k"},
            ),
            patch("app.domains.graph.router.StockwireClient") as MockClient,
        ):
            MockClient.return_value.resolve_asset = AsyncMock(return_value=resolved)
            bound = await client.post(
                f"{BASE}/jobs/{job_id}/graph/devices/{device_id}/bind-asset",
                json={"code": "TAG-42", "asset_id": "42", "expected_revision": 1},
                headers=auth_headers,
            )
        assert bound.status_code == 200, bound.text
        attrs = bound.json()["attributes"]
        assert attrs.get("stockwire_asset_id") is None
        assert attrs["stockwire_asset_code"] == "TAG-42"
        assert bound.json()["stockwire_device_id"] == "42"
        MockClient.return_value.resolve_asset.assert_awaited_once_with("42")


async def test_picker_binding_keeps_selected_id_if_stockwire_resolution_fails(
    auth_headers,
):
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        job_id, device_id = await _make_job_and_device(client, auth_headers)
        with (
            patch(
                "app.domains.graph.router.load_integration_config",
                return_value={"enabled": True, "base_url": "http://stockwire", "api_key": "k"},
            ),
            patch("app.domains.graph.router.StockwireClient") as MockClient,
        ):
            MockClient.return_value.resolve_asset = AsyncMock(return_value=None)
            bound = await client.post(
                f"{BASE}/jobs/{job_id}/graph/devices/{device_id}/bind-asset",
                json={
                    "code": "TAG-42",
                    "asset_id": "42",
                    "tag": "TAG-42",
                    "expected_revision": 1,
                },
                headers=auth_headers,
            )
        assert bound.status_code == 200, bound.text
        attrs = bound.json()["attributes"]
        assert attrs.get("stockwire_asset_id") is None
        assert attrs["stockwire_asset_code"] == "TAG-42"
        assert attrs["stockwire_asset_tag"] == "TAG-42"
        assert bound.json()["stockwire_device_id"] == "42"


async def test_picker_binding_rejects_an_asset_from_a_different_product(auth_headers):
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        job = await client.post(
            f"{BASE}/jobs", json={"title": "Product binding"}, headers=auth_headers
        )
        job_id = job.json()["id"]
        device = await client.post(
            f"{BASE}/jobs/{job_id}/graph/devices",
            json={
                "domain": "audio",
                "name": "Stagebox",
                "kind": "stagebox",
                "stockwire_product_id": "77",
            },
            headers=auth_headers,
        )
        resolved = {"asset_id": "42", "product_id": "88"}
        with (
            patch(
                "app.domains.graph.router.load_integration_config",
                return_value={"enabled": True, "base_url": "http://stockwire", "api_key": "k"},
            ),
            patch("app.domains.graph.router.StockwireClient") as MockClient,
        ):
            MockClient.return_value.resolve_asset = AsyncMock(return_value=resolved)
            bound = await client.post(
                f"{BASE}/jobs/{job_id}/graph/devices/{device.json()['id']}/bind-asset",
                json={"code": "TAG-42", "asset_id": "42", "expected_revision": 1},
                headers=auth_headers,
            )
        assert bound.status_code == 422
        assert "does not belong to the linked product" in bound.json()["detail"]


async def test_bind_rejects_stale_device_revision(auth_headers):
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        job_id, device_id = await _make_job_and_device(client, auth_headers)
        first = await client.post(
            f"{BASE}/jobs/{job_id}/graph/devices/{device_id}/bind-asset",
            json={"code": "ASSET-1", "expected_revision": 1},
            headers=auth_headers,
        )
        assert first.status_code == 200
        stale = await client.post(
            f"{BASE}/jobs/{job_id}/graph/devices/{device_id}/bind-asset",
            json={"code": "ASSET-2", "expected_revision": 1},
            headers=auth_headers,
        )
        assert stale.status_code == 409
        assert stale.json()["detail"]["code"] == "revision_conflict"
