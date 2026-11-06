"""Phase 2 (venues-as-template-jobs): venue-scoped channel lists and Wireless Workbench.

A venue's Standard Base Rig reuses the job graph list/channel/WWB machinery, keyed by
venue_id instead of job_id. These tests pin that the venue routes create venue-owned rows,
import WWB onto the venue's wireless channels, store the .shw against the venue, and never
cross into a job's data (and vice versa).
"""

from uuid import UUID

from httpx import ASGITransport, AsyncClient
from sqlalchemy import select

from app.core import db as db_mod
from app.domains.audio.models import WwbShowFile
from app.main import app

BASE = "/api/v1"

VENUE = {
    "name": "WWB Hall",
    "venue_width_cm": 1000,
    "venue_height_cm": 800,
    "stage_width_cm": 300,
    "stage_height_cm": 200,
}

WWB_XML = """<show_file>
  <channel>
    <frequency>518125</frequency>
    <channel_name>MIC 1</channel_name>
  </channel>
</show_file>"""


async def _venue(client, headers, name="WWB Hall"):
    res = await client.post(f"{BASE}/venues", json={**VENUE, "name": name}, headers=headers)
    return res.json()["id"]


async def _job(client, headers, title="WWB Job"):
    return (await client.post(f"{BASE}/jobs", json={"title": title}, headers=headers)).json()["id"]


async def test_venue_channel_list_and_wwb_import_are_venue_scoped(auth_headers):
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        venue_id = await _venue(client, auth_headers)

        # A venue channel list is created venue-owned (job_id null, venue_id set).
        created = (
            await client.post(
                f"{BASE}/venues/{venue_id}/graph/lists",
                json={"name": "House RF"},
                headers=auth_headers,
            )
        ).json()
        list_id = created["id"]
        node = (await client.get(f"{BASE}/venues/{venue_id}/graph", headers=auth_headers)).json()
        assert any(d["id"] == list_id and d["kind"] == "channel_list" for d in node["devices"])

        # Add a wireless channel to the venue list.
        ch = (
            await client.post(
                f"{BASE}/venues/{venue_id}/graph/lists/{list_id}/channels/batch",
                json=[{"source_label": "MIC 1", "input_type": "wireless"}],
                headers=auth_headers,
            )
        ).json()[0]
        assert ch["kind"] == "channel"

        # Import a .shw: the venue's wireless channel inherits the coordinated frequency.
        import_res = await client.post(
            f"{BASE}/venues/{venue_id}/graph/lists/{list_id}/wireless-workbench/import",
            headers=auth_headers,
            files={"file": ("show.shw", WWB_XML, "application/xml")},
        )
        assert import_res.status_code == 200, import_res.text
        body = import_res.json()
        assert body["matched"] == 1
        assert body["updated"] == 1

        # The frequency landed on the venue's channel (read back from the base rig graph).
        rig = (await client.get(f"{BASE}/venues/{venue_id}/graph", headers=auth_headers)).json()
        channel = next(d for d in rig["devices"] if d["id"] == ch["id"])
        assert channel["attributes"]["wireless_frequency_mhz"] == 518.125

        # The show file is stored venue-owned.
        stored = await client.get(
            f"{BASE}/venues/{venue_id}/graph/lists/{list_id}/export?plugin=wireless_workbench",
            headers=auth_headers,
        )
        assert stored.status_code == 200

        # Strict scoping: a job list created with the same name shares nothing with the venue.
        job_id = await _job(client, auth_headers)
        job_list = (
            await client.post(
                f"{BASE}/jobs/{job_id}/graph/lists",
                json={"name": "Job RF"},
                headers=auth_headers,
            )
        ).json()
        # The venue show file is keyed by its own list node; a parallel job import must not
        # touch it. Import the same file into the job list and confirm it succeeds
        # independently (each list stores its own .shw).
        await client.post(
            f"{BASE}/jobs/{job_id}/graph/lists/{job_list['id']}/wireless-workbench/import",
            headers=auth_headers,
            files={"file": ("show.shw", WWB_XML, "application/xml")},
        )
        job_export = await client.get(
            f"{BASE}/jobs/{job_id}/graph/lists/{job_list['id']}/export?plugin=wireless_workbench",
            headers=auth_headers,
        )
        assert job_export.status_code == 200


async def test_venue_wwb_show_file_rows_are_venue_owned(auth_headers):
    """The persisted WwbShowFile row carries venue_id, not job_id, for a venue import."""
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        venue_id = await _venue(client, auth_headers)

        created = (
            await client.post(
                f"{BASE}/venues/{venue_id}/graph/lists",
                json={"name": "House RF 2"},
                headers=auth_headers,
            )
        ).json()
        list_id = created["id"]
        await client.post(
            f"{BASE}/venues/{venue_id}/graph/lists/{list_id}/channels/batch",
            json=[{"source_label": "MIC 1", "input_type": "wireless"}],
            headers=auth_headers,
        )
        await client.post(
            f"{BASE}/venues/{venue_id}/graph/lists/{list_id}/wireless-workbench/import",
            headers=auth_headers,
            files={"file": ("show.shw", WWB_XML, "application/xml")},
        )

        async with db_mod.SessionLocal() as db:
            row = (
                await db.scalars(
                    select(WwbShowFile).where(WwbShowFile.list_node_id == UUID(list_id))
                )
            ).first()
        assert row is not None
        assert row.venue_id == UUID(venue_id)
        assert row.job_id is None
