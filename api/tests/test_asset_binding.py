"""Binding a physical Stockwire inventory asset to a Stagewire device.

The bind records the scanned/typed code locally (as ``stockwire_asset_code`` and, when the
integration is disabled, also as ``stockwire_asset_id``); when the integration is enabled the
code is resolved and the canonical Stockwire id/tag/serial/description are captured too. The
raw code is always kept so the crew view can look devices up by the value a user actually scans.
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

        # No Stockwire integration in tests → local binding, code stored as asset id.
        bound = await client.post(
            f"{BASE}/jobs/{job_id}/graph/devices/{device_id}/bind-asset",
            json={"code": "ASSET-999", "tag": "TAG-999", "serial": "SN-999"},
            headers=auth_headers,
        )
        assert bound.status_code == 200, bound.text
        attrs = bound.json()["attributes"]
        assert attrs["stockwire_asset_id"] == "ASSET-999"
        assert attrs["stockwire_asset_code"] == "ASSET-999"
        assert attrs["stockwire_asset_tag"] == "TAG-999"
        assert attrs["stockwire_asset_serial"] == "SN-999"

        # The device read from the graph reflects the binding.
        graph = (await client.get(f"{BASE}/jobs/{job_id}/graph", headers=auth_headers)).json()
        device = next(d for d in graph["devices"] if d["id"] == device_id)
        assert device["attributes"]["stockwire_asset_id"] == "ASSET-999"
        assert device["attributes"]["stockwire_asset_code"] == "ASSET-999"


async def test_bind_asset_requires_job_scope(auth_headers):
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        job_id, device_id = await _make_job_and_device(client, auth_headers)
        # A device from a different (nonexistent) job must 404, not bind cross-job.
        other = await client.post(
            f"{BASE}/jobs/00000000-0000-0000-0000-000000000000/graph/devices/{device_id}/bind-asset",
            json={"code": "X"},
            headers=auth_headers,
        )
        assert other.status_code == 404


async def test_bind_keeps_raw_code_separate_from_resolved_id(auth_headers):
    """High fix: with the integration on, the scanned code must survive on its own key.

    Resolution stores the canonical Stockwire asset id on ``stockwire_asset_id``, but the
    crew view looks devices up by the code a user scans — so ``stockwire_asset_code`` must
    hold the raw scanned value regardless.
    """
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        job_id, device_id = await _make_job_and_device(client, auth_headers)
        resolved = {
            "asset_id": "42",
            "asset_tag": "TAG-42",
            "serial_number": "SN-42",
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
                json={"code": "ASSET-RAW"},
                headers=auth_headers,
            )
        assert bound.status_code == 200, bound.text
        attrs = bound.json()["attributes"]
        assert attrs["stockwire_asset_code"] == "ASSET-RAW"  # raw scanned value
        assert attrs["stockwire_asset_id"] == "42"  # canonical resolved id
        assert attrs["stockwire_asset_tag"] == "TAG-42"
