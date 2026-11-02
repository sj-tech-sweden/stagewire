import io
import re
import zipfile

import pytest
from audio_seed import seed_channel, seed_list, seed_output
from httpx import ASGITransport, AsyncClient

from app.core import db as db_mod
from app.domains.audio.exports import list_exporters
from app.domains.audio.models import (
    ProductionJob,
)
from app.main import app

BASE = "/api/v1"


async def _seed() -> tuple[str, str]:
    async with db_mod.SessionLocal() as db:
        job = ProductionJob(title="Export parity")
        db.add(job)
        await db.flush()
        lst = await seed_list(
            db, job.id, name="FOH / Main", mixer_product_name="Qu-32", mixer_inputs=32
        )
        await seed_channel(
            db,
            lst,
            channel_number=1,
            source_label="Kick",
            input_type="microphone",
            connector="XLR",
            device="Beta 91",
            stand_type="Short boom",
            phantom_power=True,
            notes="inside the drum",
        )
        await seed_channel(
            db,
            lst,
            channel_number=3,
            source_label="Keys",
            input_type="di",
            stereo=True,
            stereo_channel=1,
            color_code="blue",
        )
        await seed_channel(db, lst, channel_number=2, source_label="Snare")
        await seed_output(
            db, lst, name="Mon 1", position=0, mode="stereo", connector="XLR", notes="wedge"
        )
        await seed_output(db, lst, name="Mon 2", position=1)
        await db.commit()
        return str(job.id), str(lst.id)


def _members(content: bytes) -> dict[str, bytes]:
    with zipfile.ZipFile(io.BytesIO(content)) as zf:
        return {
            name: re.sub(rb"\d{4}-\d\d-\d\dT[\d:]+Z?", b"", zf.read(name))
            for name in zf.namelist()
            if not name.endswith("core.xml")
        }


@pytest.mark.asyncio
async def test_graph_export_matches_legacy_for_every_plugin(auth_headers):
    job_id, legacy_list_id = await _seed()
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        g = f"{BASE}/jobs/{job_id}/graph"
        await client.post(f"{g}/backfill", headers=auth_headers)
        graph = (await client.get(g, headers=auth_headers)).json()
        container = next(d for d in graph["devices"] if d["kind"] == "channel_list")
        assert container["name"] == "FOH / Main"

        plugins = (await client.get(f"{g}/export-plugins", headers=auth_headers)).json()
        assert {p["key"] for p in plugins} == {e.key for e in list_exporters()}
        for plugin in plugins:
            legacy = await client.get(
                f"{BASE}/jobs/{job_id}/channel-lists/{legacy_list_id}/export",
                params={"plugin": plugin["key"]},
                headers=auth_headers,
            )
            new = await client.get(
                f"{g}/lists/{container['id']}/export",
                params={"plugin": plugin["key"]},
                headers=auth_headers,
            )
            assert legacy.status_code == new.status_code == 200, plugin["key"]
            assert new.headers["content-disposition"] == legacy.headers["content-disposition"]
            if legacy.content != new.content:
                assert _members(legacy.content) == _members(new.content), plugin["key"]


@pytest.mark.asyncio
async def test_graph_export_follows_graph_edits_and_rejects_bad_requests(auth_headers):
    job_id, _ = await _seed()
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        g = f"{BASE}/jobs/{job_id}/graph"
        await client.post(f"{g}/backfill", headers=auth_headers)
        devices = (await client.get(g, headers=auth_headers)).json()["devices"]
        container = next(d for d in devices if d["kind"] == "channel_list")
        kick = next(d for d in devices if d["name"] == "Kick")
        await client.patch(
            f"{g}/devices/{kick['id']}",
            json={"name": "Kick In", "expected_revision": kick["revision"]},
            headers=auth_headers,
        )
        csv = await client.get(
            f"{g}/lists/{container['id']}/export",
            params={"plugin": "generic_csv"},
            headers=auth_headers,
        )
        assert b"Kick In" in b"".join(_members(csv.content).values())

        assert (
            await client.get(
                f"{g}/lists/{container['id']}/export",
                params={"plugin": "nope"},
                headers=auth_headers,
            )
        ).status_code == 404
        assert (
            await client.get(
                f"{g}/lists/{kick['id']}/export",
                params={"plugin": "generic_csv"},
                headers=auth_headers,
            )
        ).status_code == 404
