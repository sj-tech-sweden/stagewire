"""Undo, redo and restore: every write is recorded as a row diff and can be stepped through."""

import pytest
from httpx import ASGITransport, AsyncClient

from app.main import app

BASE = "/api/v1"


async def _job(client, h):
    job_id = (await client.post(f"{BASE}/jobs", json={"title": "History"}, headers=h)).json()["id"]
    api = f"{BASE}/jobs/{job_id}"

    async def post(path, body, expect=201):
        res = await client.post(f"{api}/{path}", json=body, headers=h)
        assert res.status_code == expect, res.text
        return res.json()

    return job_id, api, post


async def _history(client, h, api):
    return (await client.get(f"{api}/history", headers=h)).json()


async def _channels(client, h, api):
    lists = (await client.get(f"{api}/channel-lists", headers=h)).json()
    return {c["id"]: c for lst in lists for c in lst["channels"]}


@pytest.mark.asyncio
async def test_writes_are_recorded_and_undo_redo_restore_the_exact_rows(auth_headers):
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        h = auth_headers
        _, api, post = await _job(client, h)
        before = await _history(client, h, api)
        assert before["entries"] == [] and not before["can_undo"]
        lst = await post("channel-lists", {"name": "FOH"})
        ch = await post(
            f"channel-lists/{lst['id']}/channels", {"channel_number": 1, "source_label": "Vox"}
        )
        state = await _history(client, h, api)
        assert [e["label"] for e in state["entries"]] == ["Create channel", "Create channel list"]
        assert state["entries"][0]["summary"] == "Vox" and state["can_undo"]

        # undo removes the channel (and its graph node); redo brings back the very same id
        undone = await client.post(f"{api}/history/undo", headers=h)
        assert undone.status_code == 200, undone.text
        assert undone.json()["applied"]["label"] == "Create channel" and undone.json()["can_redo"]
        assert ch["id"] not in await _channels(client, h, api)
        redone = await client.post(f"{api}/history/redo", headers=h)
        assert redone.status_code == 200, redone.text
        assert (await _channels(client, h, api))[ch["id"]]["source_label"] == "Vox"
        # undo and redo are not themselves history entries
        assert len((await _history(client, h, api))["entries"]) == 2


@pytest.mark.asyncio
async def test_an_edit_is_undone_to_the_old_values(auth_headers):
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        h = auth_headers
        job_id, api, post = await _job(client, h)
        lst = await post("channel-lists", {"name": "FOH"})
        ch = await post(
            f"channel-lists/{lst['id']}/channels", {"channel_number": 1, "source_label": "Vox"}
        )
        res = await client.patch(
            f"{api}/channels/{ch['id']}",
            json={"source_label": "Lead", "phantom_power": True, "expected_revision": 1},
            headers=h,
        )
        assert res.status_code == 200
        title = await client.patch(f"{api}", json={"title": "Renamed"}, headers=h)
        assert title.status_code == 200
        assert (await client.get(api, headers=h)).json()["title"] == "Renamed"
        await client.post(f"{api}/history/undo", headers=h)  # the job title
        assert (await client.get(api, headers=h)).json()["title"] == "History"
        await client.post(f"{api}/history/undo", headers=h)  # the channel edit
        row = (await _channels(client, h, api))[ch["id"]]
        assert row["source_label"] == "Vox" and row["phantom_power"] is False
        await client.post(f"{api}/history/redo", headers=h)
        row = (await _channels(client, h, api))[ch["id"]]
        assert row["source_label"] == "Lead" and row["phantom_power"] is True


@pytest.mark.asyncio
async def test_deleting_a_channel_is_undone_with_its_cables(auth_headers):
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        h = auth_headers
        _, api, post = await _job(client, h)
        lst = await post("channel-lists", {"name": "FOH"})
        ch = await post(
            f"channel-lists/{lst['id']}/channels", {"channel_number": 1, "source_label": "Vox"}
        )
        box = await post("devices", {"name": "Box", "device_type": "analog_stagebox"})
        await post(
            f"channels/{ch['id']}/patch-points", {"device_id": box["id"], "connector": "XLR"}
        )

        async def edges():
            graph = (await client.get(f"{api}/graph", headers=h)).json()
            return [
                e for e in graph["edges"] if ch["id"] in (e["src_device_id"], e["dst_device_id"])
            ]

        assert len(await edges()) == 1
        gone = await client.delete(
            f"{api}/channels/{ch['id']}",
            params={"expected_revision": (await _channels(client, h, api))[ch["id"]]["revision"]},
            headers=h,
        )
        assert gone.status_code == 204
        assert await edges() == []
        assert (await client.post(f"{api}/history/undo", headers=h)).status_code == 200
        assert ch["id"] in await _channels(client, h, api)
        assert len(await edges()) == 1  # the cable came back with the channel


@pytest.mark.asyncio
async def test_restore_to_a_version_and_a_new_change_ends_the_redo_stack(auth_headers):
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        h = auth_headers
        _, api, post = await _job(client, h)
        lst = await post("channel-lists", {"name": "FOH"})
        ids = []
        for n in range(1, 4):
            ids.append(
                (await post(f"channel-lists/{lst['id']}/channels", {"channel_number": n}))["id"]
            )
        entries = (await _history(client, h, api))["entries"]
        assert [e["seq"] for e in entries] == [4, 3, 2, 1]
        # step back to the version right after the first channel was made
        res = await client.post(f"{api}/history/restore", json={"seq": 2}, headers=h)
        assert res.status_code == 200 and res.json()["steps"] == 2 and res.json()["cursor"] == 2
        assert set(await _channels(client, h, api)) == {ids[0]}
        # ... and forward again
        res = await client.post(f"{api}/history/restore", json={"seq": 4}, headers=h)
        assert set(await _channels(client, h, api)) == set(ids)
        # all the way back to before anything was recorded
        await client.post(f"{api}/history/restore", json={"seq": 0}, headers=h)
        assert await client.get(f"{api}/channel-lists", headers=h)
        assert (await client.get(f"{api}/channel-lists", headers=h)).json() == []
        assert (await client.post(f"{api}/history/undo", headers=h)).status_code == 409
        # step to seq 2, then make a new change: the later versions are gone
        await client.post(f"{api}/history/restore", json={"seq": 2}, headers=h)
        await post("channel-lists", {"name": "Monitors"})
        state = await _history(client, h, api)
        assert not state["can_redo"] and [e["seq"] for e in state["entries"]] == [3, 2, 1]
        assert (await client.post(f"{api}/history/redo", headers=h)).status_code == 409
        unknown = await client.post(f"{api}/history/restore", json={"seq": 99}, headers=h)
        assert unknown.status_code == 404


@pytest.mark.asyncio
async def test_an_untracked_change_blocks_undo_unless_forced(auth_headers):
    from app.core import db as db_mod
    from app.domains.graph.models import GraphDevice

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        h = auth_headers
        _, api, post = await _job(client, h)
        lst = await post("channel-lists", {"name": "FOH"})
        ch = await post(f"channel-lists/{lst['id']}/channels", {"channel_number": 1})
        await client.patch(
            f"{api}/channels/{ch['id']}",
            json={"source_label": "Lead", "expected_revision": 1},
            headers=h,
        )
        # something changes the same row without going through a recorded request
        async with db_mod.SessionLocal() as db:
            import uuid

            node = await db.get(GraphDevice, uuid.UUID(ch["id"]))
            node.attributes = {**node.attributes, "source_label": "Sneaky"}
            await db.commit()
        blocked = await client.post(f"{api}/history/undo", headers=h)
        assert blocked.status_code == 409
        assert "changed outside the history" in blocked.json()["detail"]["message"]
        assert (await _channels(client, h, api))[ch["id"]]["source_label"] == "Sneaky"
        forced = await client.post(f"{api}/history/undo?force=true", headers=h)
        assert forced.status_code == 200
        assert (await _channels(client, h, api))[ch["id"]]["source_label"] == ""


@pytest.mark.asyncio
async def test_venues_have_their_own_history(auth_headers):
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        h = auth_headers
        venue = (await client.post(f"{BASE}/venues", json={"name": "Hall"}, headers=h)).json()
        vapi = f"{BASE}/venues/{venue['id']}"
        res = await client.patch(vapi, json={"name": "Big Hall"}, headers=h)
        assert res.status_code == 200, res.text
        state = (await client.get(f"{vapi}/history", headers=h)).json()
        assert state["can_undo"] and state["entries"][0]["summary"] == "Big Hall"
        assert (await client.post(f"{vapi}/history/undo", headers=h)).status_code == 200
        assert (await client.get(vapi, headers=h)).json()["name"] == "Hall"
        # a job's history is a different list
        _, api, _ = await _job(client, h)
        assert (await _history(client, h, api))["entries"] == []
        assert (
            await client.get(f"{BASE}/jobs/{venue['id']}/history", headers=h)
        ).status_code == 404


@pytest.mark.asyncio
async def test_a_job_date_edit_can_be_undone_and_steps_carry_a_translatable_action_key(
    auth_headers,
):
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        h = auth_headers
        _, api, post = await _job(client, h)
        res = await client.patch(api, json={"start_date": "2026-05-01"}, headers=h)
        assert res.status_code == 200, res.text
        state = await _history(client, h, api)
        assert state["entries"][0]["action"] == "update_job"  # the key the client translates
        undone = await client.post(f"{api}/history/undo", headers=h)
        assert undone.status_code == 200, undone.text  # a Date column round-trips through the diff
        assert (await client.get(api, headers=h)).json().get("start_date") in (None, "")
        redone = await client.post(f"{api}/history/redo", headers=h)
        assert redone.status_code == 200
        assert (await client.get(api, headers=h)).json()["start_date"] == "2026-05-01"


@pytest.mark.asyncio
async def test_a_failed_restore_step_rolls_everything_back(auth_headers):
    from app.core import db as db_mod
    from app.domains.graph.models import GraphDevice

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        h = auth_headers
        _, api, post = await _job(client, h)
        lst = await post("channel-lists", {"name": "FOH"})
        ch = await post(f"channel-lists/{lst['id']}/channels", {"channel_number": 1})
        await client.patch(
            f"{api}/channels/{ch['id']}",
            json={"source_label": "A", "expected_revision": 1},
            headers=h,
        )
        row = (await _channels(client, h, api))[ch["id"]]
        await client.patch(
            f"{api}/channels/{ch['id']}",
            json={"source_label": "B", "expected_revision": row["revision"]},
            headers=h,
        )
        # an untracked change makes the OLDER of the two undo steps conflict
        async with db_mod.SessionLocal() as db:
            import uuid

            node = await db.get(GraphDevice, uuid.UUID(ch["id"]))
            node.attributes = {**node.attributes, "source_label": "Sneaky"}
            await db.commit()
        # restoring to before everything needs both steps; the first conflicts, so nothing changes
        res = await client.post(f"{api}/history/restore", json={"seq": 0}, headers=h)
        assert res.status_code == 409
        state = await _history(client, h, api)
        assert state["cursor"] == 4 and not state["can_redo"]  # no step was left half-applied
        assert (await _channels(client, h, api))[ch["id"]]["source_label"] == "Sneaky"


def test_timestamps_never_count_as_an_outside_change():
    """PostgreSQL returns an aware timestamp for the naive local time the app wrote."""
    from datetime import UTC, datetime

    from app.domains.graph.models import GraphDevice
    from app.domains.history import service

    row = GraphDevice(name="X", domain="audio", created_at=datetime(2026, 1, 1, 12, 0, tzinfo=UTC))
    recorded = {"name": "X", "created_at": "2026-01-01T12:00:00"}  # as the recorder saw it
    assert service._differs(row, recorded) is False
    assert service._differs(row, {"name": "Y"}) is True


@pytest.mark.asyncio
async def test_deleting_a_job_purges_its_history(auth_headers):
    from sqlalchemy import func, select

    from app.core import db as db_mod
    from app.domains.history.models import HistoryEntry

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        h = auth_headers
        job_id, api, post = await _job(client, h)
        await post("channel-lists", {"name": "FOH"})
        assert len((await _history(client, h, api))["entries"]) == 1
        assert (await client.delete(api, headers=h)).status_code == 204
        async with db_mod.SessionLocal() as db:
            left = await db.scalar(
                select(func.count())
                .select_from(HistoryEntry)
                .where(HistoryEntry.scope_id == uuid_of(job_id))
            )
        assert left == 0


def uuid_of(value):
    import uuid

    return uuid.UUID(value)


@pytest.mark.asyncio
async def test_replacing_a_venue_base_rig_can_be_undone(auth_headers):
    from uuid import uuid4

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        h = auth_headers
        venue = (await client.post(f"{BASE}/venues", json={"name": "Rig"}, headers=h)).json()
        vapi = f"{BASE}/venues/{venue['id']}"
        a, b = str(uuid4()), str(uuid4())

        def device(ident, name):
            return {
                "id": ident,
                "domain": "audio",
                "kind": "speaker",
                "name": name,
                "attributes": {},
                "ports": [],
            }

        first = {
            "devices": [device(a, "A"), device(b, "B")],
            "edges": [
                {
                    "id": str(uuid4()),
                    "signal": "audio",
                    "src_device_id": a,
                    "src_port": "out",
                    "dst_device_id": b,
                    "dst_port": "in",
                }
            ],
        }
        assert (await client.put(f"{vapi}/graph", json=first, headers=h)).status_code == 200
        second = {"devices": [device(a, "A renamed")], "edges": []}
        assert (await client.put(f"{vapi}/graph", json=second, headers=h)).status_code == 200
        undone = await client.post(f"{vapi}/history/undo", headers=h)
        assert undone.status_code == 200, undone.text
        rig = (await client.get(f"{vapi}/graph", headers=h)).json()
        # the old rig is back: both devices (A under its old name) and the cable between them
        assert sorted(d["name"] for d in rig["devices"]) == ["A", "B"] and len(rig["edges"]) == 1
