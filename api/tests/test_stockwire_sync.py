"""Regression guard for the Stagewire → Stockwire requirement sync.

The sync may only remove rental requirements it created itself. Requirements a human
added in the rental job, or that Stagewire pushed through the separate "request to
add" flow, must survive. The invariant is tracked by ``StockwireRequirementLink``
rows: no link, no deletion.
"""

import pytest
from httpx import ASGITransport, AsyncClient

from app.domains.audio import router as audio_router
from app.main import app

BASE = "/api/v1"


class FakeRemote:
    """In-memory stand-in for the rental job's requirements.

    All instances share the same state: the sync constructs a fresh client per call.
    """

    requirements: dict[int, dict] = {}
    deleted: list[int] = []
    next_id = 1000

    @classmethod
    def reset(cls, requirements: dict[int, dict] | None = None) -> None:
        cls.requirements = dict(requirements or {})
        cls.deleted = []
        cls.next_id = 1000

    def __init__(self, *args, **kwargs) -> None:
        pass

    async def add_requirement(self, job_id, body):
        requirement_id = FakeRemote.next_id
        FakeRemote.next_id += 1
        FakeRemote.requirements[requirement_id] = dict(body)
        return {"id": requirement_id}

    async def update_requirement(self, requirement_id, body):
        FakeRemote.requirements[requirement_id].update(body)
        return {}

    async def delete_requirement(self, requirement_id):
        FakeRemote.deleted.append(requirement_id)
        FakeRemote.requirements.pop(requirement_id, None)
        return True


@pytest.fixture
def fake_stockwire(monkeypatch):
    """Point the sync at the fake rental job, pre-seeded with manual requirements."""

    async def config(db):
        return {"api_key": "k", "base_url": "http://sw"}

    FakeRemote.reset({5000: {"product_id": 200, "label": "Manual pickup"}})
    monkeypatch.setattr(audio_router, "load_integration_config", config)
    monkeypatch.setattr(audio_router, "StockwireClient", FakeRemote)
    return FakeRemote


async def _linked_job(client, h):
    job_id = (await client.post(f"{BASE}/jobs", json={"title": "Sync"}, headers=h)).json()["id"]
    api = f"{BASE}/jobs/{job_id}"
    assert (await client.patch(api, json={"stockwire_job_id": "77"}, headers=h)).status_code == 200
    return job_id, api


async def _add_gear(client, h, api, name: str, product_id: int):
    response = await client.post(
        f"{api}/devices",
        json={
            "name": name,
            "device_type": "mic",
            "stockwire_product_id": str(product_id),
            "stockwire_product_name": name,
        },
        headers=h,
    )
    assert response.status_code == 201, response.text
    return response.json()


@pytest.mark.asyncio
async def test_manual_rental_requirement_survives_sync(auth_headers, fake_stockwire):
    """A human-added rental requirement is never touched, on add or on remove."""
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        h = auth_headers
        _, api = await _linked_job(client, h)
        await _add_gear(client, h, api, "Stagewire mic", 100)

        added = await client.post(f"{api}/sync-stockwire", headers=h)
        assert added.status_code == 200, added.text
        assert added.json()["added"] == ["Stagewire mic ×1"]
        assert fake_stockwire.deleted == []
        assert 5000 in fake_stockwire.requirements  # the manual requirement is untouched

        device = (await client.get(f"{api}/devices", headers=h)).json()[0]
        assert (await client.delete(f"{api}/devices/{device['id']}", headers=h)).status_code == 204

        removed = await client.post(f"{api}/sync-stockwire", headers=h)
        assert removed.status_code == 200, removed.text
        assert removed.json()["removed"] == ["Stagewire mic"]
        # Only the requirement this sync created (id 1000) goes; the manual one stays.
        assert fake_stockwire.deleted == [1000]
        assert 5000 in fake_stockwire.requirements


@pytest.mark.asyncio
async def test_stagewire_requirement_removed_with_gear(auth_headers, fake_stockwire):
    """The other half of the rule: a synced item is removed after Stagewire drops it."""
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        h = auth_headers
        _, api = await _linked_job(client, h)
        await _add_gear(client, h, api, "Console", 101)

        assert (await client.post(f"{api}/sync-stockwire", headers=h)).json()["added"] == [
            "Console ×1"
        ]
        assert 1000 in fake_stockwire.requirements

        device = (await client.get(f"{api}/devices", headers=h)).json()[0]
        assert (await client.delete(f"{api}/devices/{device['id']}", headers=h)).status_code == 204

        result = await client.post(f"{api}/sync-stockwire", headers=h)
        assert result.status_code == 200, result.text
        assert result.json()["removed"] == ["Console"]
        assert fake_stockwire.deleted == [1000]
        assert 1000 not in fake_stockwire.requirements


@pytest.mark.asyncio
async def test_request_to_add_link_is_recorded_but_never_reconciled(auth_headers, fake_stockwire):
    """A direct "request to add" is Stagewire-created, but not a plot mirror.

    It gets its own link so future readers can tell it apart from a sync-owned
    requirement; the product-level sync must leave it alone.
    """
    from sqlalchemy import select

    from app.core.db import SessionLocal
    from app.domains.audio.models import StockwireRequirementLink
    from app.domains.graph.router import get_stockwire_client

    class RequestClient:
        async def add_requirement(self, job_id, body):
            FakeRemote.requirements[2001] = dict(body)
            return {"id": 2001}

    app.dependency_overrides[get_stockwire_client] = lambda: RequestClient()
    try:
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            h = auth_headers
            _, api = await _linked_job(client, h)
            graph = f"{api}/graph"
            device = (
                await client.post(
                    f"{graph}/devices",
                    json={
                        "domain": "audio",
                        "name": "Requested mic",
                        "stockwire_product_id": "300",
                        "stockwire_booked": False,
                    },
                    headers=h,
                )
            ).json()
            requested = await client.post(
                f"{graph}/devices/{device['id']}/request-stockwire", headers=h
            )
            assert requested.status_code == 200, requested.text

            async with SessionLocal() as db:
                link = (
                    (
                        await db.execute(
                            select(StockwireRequirementLink).where(
                                StockwireRequirementLink.item_key == f"request:{device['id']}"
                            )
                        )
                    )
                    .scalars()
                    .one()
                )
                assert link.source == "request"
                assert link.rental_requirement_id == 2001

            # A synced product comes and goes; the standing request is untouched.
            await _add_gear(client, h, api, "Stagewire mic", 100)
            assert (await client.post(f"{api}/sync-stockwire", headers=h)).json()["added"] == [
                "Stagewire mic ×1"
            ]
            gear = (await client.get(f"{api}/devices", headers=h)).json()[0]
            deleted_gear = await client.delete(f"{api}/devices/{gear['id']}", headers=h)
            assert deleted_gear.status_code == 204
            result = await client.post(f"{api}/sync-stockwire", headers=h)
            assert result.status_code == 200, result.text
            assert fake_stockwire.deleted == [1000]
            assert 2001 in fake_stockwire.requirements
    finally:
        app.dependency_overrides.pop(get_stockwire_client, None)


@pytest.mark.asyncio
async def test_unchanged_sync_deletes_nothing(auth_headers, fake_stockwire):
    """A repeat sync with no Stagewire changes must not delete or re-add anything."""
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        h = auth_headers
        _, api = await _linked_job(client, h)
        await _add_gear(client, h, api, "Mic", 102)

        first = await client.post(f"{api}/sync-stockwire", headers=h)
        assert first.status_code == 200, first.text
        second = await client.post(f"{api}/sync-stockwire", headers=h)
        assert second.status_code == 200, second.text
        assert second.json()["added"] == [] and second.json()["removed"] == []
        assert second.json()["unchanged"] == 1
        assert fake_stockwire.deleted == []
        assert 5000 in fake_stockwire.requirements
