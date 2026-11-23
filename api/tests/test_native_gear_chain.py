"""A soft-patched channel's chain hop must survive the graph sync for native (no-ref) gear."""

import uuid

import pytest
from audio_seed import seed_channel, seed_list
from httpx import ASGITransport, AsyncClient

from app.core import db as db_mod
from app.domains.audio.models import ProductionJob
from app.domains.graph.models import GraphDevice
from app.main import app

BASE = "/api/v1"


@pytest.mark.asyncio
async def test_native_stagebox_patch_hop_is_synced_into_the_graph(auth_headers):
    """Regression: production stageboxes created via /graph/devices have no legacy_ref. The sync's
    channel patch-point loop used to skip those devices, so the soft patch and chain editor agreed
    but the graph edge (and thus the signal flow / reports) lost the stagebox entirely."""
    async with db_mod.SessionLocal() as db:
        job = ProductionJob(title="Native gear chain")
        db.add(job)
        await db.flush()
        # A native device: kind set, no legacy_ref, with the input port the channel is patched to.
        box = GraphDevice(
            id=uuid.uuid4(),
            job_id=job.id,
            domain="audio",
            kind="digital_stagebox",
            name="AR2412",
            attributes={"device_type": "digital_stagebox"},
            ports=[
                {
                    "id": "in-xlr3",
                    "direction": "in",
                    "signal": "audio",
                    "connector": "xlr3",
                    "channels": 24,
                }
            ],
        )
        db.add(box)
        await db.flush()
        lst = await seed_list(db, job.id, name="FOH")
        ch = await seed_channel(db, lst, channel_number=1, source_label="Drums")
        # The soft patch writes a chain point referencing the native box (the sync_to_chain path).
        node = await db.get(GraphDevice, ch.id)
        node.attributes = {
            **(node.attributes or {}),
            "dsp_source": {"device_id": str(box.id), "port_id": "in-xlr3", "socket": 5},
            "points": [
                {
                    "point_id": str(uuid.uuid4()),
                    "position": 0,
                    "device_id": str(box.id),
                    "connector": "xlr3",
                    "patch_label": "In 5",
                    "point_type": "digital_stagebox",
                    "soft_patch": True,
                }
            ],
        }
        await db.commit()
        job_id = str(job.id)
        box_id = str(box.id)
        ch_id = str(ch.id)

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        # The backfill runs the graph sync that turns points into edges.
        res = await client.post(f"{BASE}/jobs/{job_id}/graph/backfill", headers=auth_headers)
        assert res.status_code == 200, res.text
        graph = (await client.get(f"{BASE}/jobs/{job_id}/graph", headers=auth_headers)).json()
        edges = graph["edges"]

        # The chain hop edge points at the native stagebox and into the channel — it must exist.
        hop = next(
            (
                e
                for e in edges
                if e["src_device_id"] == box_id
                and e["dst_device_id"] == ch_id
                and (e.get("attributes") or {}).get("chain") == ch_id
            ),
            None,
        )
        assert hop is not None, "the soft-patched stagebox hop was dropped from the graph"
        assert (hop["attributes"] or {}).get("patch_label") == "In 5"

        # A second backfill must not duplicate the hop: it is keyed by the stable point id.
        again = await client.post(f"{BASE}/jobs/{job_id}/graph/backfill", headers=auth_headers)
        assert again.status_code == 200, again.text
        edges2 = (await client.get(f"{BASE}/jobs/{job_id}/graph", headers=auth_headers)).json()[
            "edges"
        ]
        hops2 = [
            e
            for e in edges2
            if e["src_device_id"] == box_id
            and e["dst_device_id"] == ch_id
            and (e.get("attributes") or {}).get("chain") == ch_id
        ]
        assert len(hops2) == 1
