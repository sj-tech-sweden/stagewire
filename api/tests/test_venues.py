import asyncio
from uuid import UUID, uuid4

from httpx import ASGITransport, AsyncClient
from sqlalchemy import select

from app.core import db as db_mod
from app.domains.audio.models import AudioDevice, ChannelList, StagePlotElement
from app.domains.lighting.models import FixtureType, LightingFixture
from app.domains.rigging.models import PowerNode, RiggingPoint
from app.domains.video.models import VideoInput, VideoInputList
from app.main import app

BASE = "/api/v1"

VENUE = {
    "name": "Main Hall",
    "venue_width_cm": 1000,
    "venue_height_cm": 800,
    "stage_x_cm": 100,
    "stage_y_cm": 50,
    "stage_width_cm": 300,
    "stage_height_cm": 200,
    "background_image_url": "/static/hall.png",
}


async def test_venue_crud_and_validation(auth_headers):
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        created = await client.post(f"{BASE}/venues", json=VENUE, headers=auth_headers)
        assert created.status_code == 201, created.text
        venue_id = created.json()["id"]
        assert created.json()["venue_width_cm"] == 1000
        assert created.json()["propagated_at"] is None

        listed = await client.get(f"{BASE}/venues", headers=auth_headers)
        assert listed.status_code == 200
        assert any(v["id"] == venue_id for v in listed.json())

        updated = await client.patch(
            f"{BASE}/venues/{venue_id}",
            json={"stage_x_cm": 150, "notes": "Load-in at the back"},
            headers=auth_headers,
        )
        assert updated.status_code == 200, updated.text
        assert updated.json()["stage_x_cm"] == 150
        assert updated.json()["venue_width_cm"] == 1000

        invalid = await client.post(
            f"{BASE}/venues", json={**VENUE, "venue_width_cm": -5}, headers=auth_headers
        )
        assert invalid.status_code == 422

        missing = await client.get(
            f"{BASE}/venues/00000000-0000-0000-0000-000000000000", headers=auth_headers
        )
        assert missing.status_code == 404

        deleted = await client.delete(f"{BASE}/venues/{venue_id}", headers=auth_headers)
        assert deleted.status_code == 204


async def test_assign_snapshots_venue_and_unassign_keeps_it(auth_headers):
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        venue = (await client.post(f"{BASE}/venues", json=VENUE, headers=auth_headers)).json()
        job = (
            await client.post(f"{BASE}/jobs", json={"title": "Gig A"}, headers=auth_headers)
        ).json()

        assigned = await client.put(
            f"{BASE}/jobs/{job['id']}/venue",
            json={"venue_id": venue["id"]},
            headers=auth_headers,
        )
        assert assigned.status_code == 200, assigned.text
        body = assigned.json()
        assert body["venue_id"] == venue["id"]
        assert body["venue_name"] == "Main Hall"
        assert body["venue_width_cm"] == 1000
        assert body["venue_height_cm"] == 800
        assert body["stage_x_cm"] == 100
        assert body["stage_y_cm"] == 50
        assert body["stage_width_cm"] == 300
        assert body["stage_height_cm"] == 200
        assert body["venue_background_image_url"] == "/static/hall.png"
        assert body["venue_footprint_shape"] == "rectangular"
        assert body["venue_stage_shape"] == "proscenium"

        unassigned = await client.put(
            f"{BASE}/jobs/{job['id']}/venue", json={"venue_id": None}, headers=auth_headers
        )
        assert unassigned.status_code == 200
        assert unassigned.json()["venue_id"] is None
        assert unassigned.json()["venue_width_cm"] == 1000

        missing = await client.put(
            f"{BASE}/jobs/{job['id']}/venue",
            json={"venue_id": "00000000-0000-0000-0000-000000000000"},
            headers=auth_headers,
        )
        assert missing.status_code == 404


async def test_deleting_venue_keeps_job_snapshot(auth_headers):
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        venue = (await client.post(f"{BASE}/venues", json=VENUE, headers=auth_headers)).json()
        job = (
            await client.post(f"{BASE}/jobs", json={"title": "Gig B"}, headers=auth_headers)
        ).json()
        await client.put(
            f"{BASE}/jobs/{job['id']}/venue", json={"venue_id": venue["id"]}, headers=auth_headers
        )

        await client.delete(f"{BASE}/venues/{venue['id']}", headers=auth_headers)

        after = (await client.get(f"{BASE}/jobs/{job['id']}", headers=auth_headers)).json()
        assert after["venue_id"] is None
        assert after["venue_width_cm"] == 1000
        assert after["stage_width_cm"] == 300


async def test_propagate_all_and_newer(auth_headers):
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        venue = (await client.post(f"{BASE}/venues", json=VENUE, headers=auth_headers)).json()
        venue_id = venue["id"]

        old_job = (
            await client.post(f"{BASE}/jobs", json={"title": "Old"}, headers=auth_headers)
        ).json()
        await client.put(
            f"{BASE}/jobs/{old_job['id']}/venue",
            json={"venue_id": venue_id},
            headers=auth_headers,
        )

        first = await client.post(
            f"{BASE}/venues/{venue_id}/propagate", json={"scope": "all"}, headers=auth_headers
        )
        assert first.status_code == 200, first.text
        assert first.json() == {"updated": 1}

        venue_after_propagate = (
            await client.get(f"{BASE}/venues/{venue_id}", headers=auth_headers)
        ).json()
        assert venue_after_propagate["propagated_at"] is not None

        await asyncio.sleep(0.01)
        new_job = (
            await client.post(f"{BASE}/jobs", json={"title": "New"}, headers=auth_headers)
        ).json()
        await client.put(
            f"{BASE}/jobs/{new_job['id']}/venue",
            json={"venue_id": venue_id},
            headers=auth_headers,
        )

        await client.patch(
            f"{BASE}/venues/{venue_id}",
            json={"venue_width_cm": 1200, "stage_width_cm": 400},
            headers=auth_headers,
        )

        newer = await client.post(
            f"{BASE}/venues/{venue_id}/propagate", json={"scope": "newer"}, headers=auth_headers
        )
        assert newer.status_code == 200, newer.text
        assert newer.json() == {"updated": 1}

        old_after = (await client.get(f"{BASE}/jobs/{old_job['id']}", headers=auth_headers)).json()
        new_after = (await client.get(f"{BASE}/jobs/{new_job['id']}", headers=auth_headers)).json()
        assert old_after["venue_width_cm"] == 1000
        assert old_after["stage_width_cm"] == 300
        assert new_after["venue_width_cm"] == 1200
        assert new_after["stage_width_cm"] == 400

        everyone = await client.post(
            f"{BASE}/venues/{venue_id}/propagate", json={"scope": "all"}, headers=auth_headers
        )
        assert everyone.json() == {"updated": 2}
        old_final = (await client.get(f"{BASE}/jobs/{old_job['id']}", headers=auth_headers)).json()
        assert old_final["venue_width_cm"] == 1200

        bad_scope = await client.post(
            f"{BASE}/venues/{venue_id}/propagate", json={"scope": "some"}, headers=auth_headers
        )
        assert bad_scope.status_code == 422


async def test_venue_geometry_shapes(auth_headers):
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        created = await client.post(
            f"{BASE}/venues",
            json={**VENUE, "footprint_shape": "arena_circular", "stage_shape": "thrust"},
            headers=auth_headers,
        )
        assert created.status_code == 201, created.text
        body = created.json()
        assert body["footprint_shape"] == "arena_circular"
        assert body["stage_shape"] == "thrust"

        defaulted = await client.post(f"{BASE}/venues", json=VENUE, headers=auth_headers)
        assert defaulted.status_code == 201, defaulted.text
        assert defaulted.json()["footprint_shape"] == "rectangular"
        assert defaulted.json()["stage_shape"] == "proscenium"

        bad = await client.post(
            f"{BASE}/venues", json={**VENUE, "footprint_shape": "hexagon"}, headers=auth_headers
        )
        assert bad.status_code == 422

        vid = created.json()["id"]
        patched = await client.patch(
            f"{BASE}/venues/{vid}", json={"stage_shape": "arena_center"}, headers=auth_headers
        )
        assert patched.status_code == 200, patched.text
        assert patched.json()["stage_shape"] == "arena_center"

        job = (
            await client.post(f"{BASE}/jobs", json={"title": "Gig shapes"}, headers=auth_headers)
        ).json()
        assigned = await client.put(
            f"{BASE}/jobs/{job['id']}/venue",
            json={"venue_id": vid},
            headers=auth_headers,
        )
        assert assigned.status_code == 200, assigned.text
        assert assigned.json()["venue_footprint_shape"] == "arena_circular"
        assert assigned.json()["venue_stage_shape"] == "arena_center"


async def test_base_rig_is_cloned_on_assign(auth_headers):
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        venue = (
            await client.post(
                f"{BASE}/venues", json={**VENUE, "name": "Base Rig Venue"}, headers=auth_headers
            )
        ).json()
        venue_id = UUID(venue["id"])

        async with db_mod.SessionLocal() as db:
            cl = ChannelList(job_id=None, venue_id=venue_id, name="House Inputs")
            dev = AudioDevice(id=uuid4(), job_id=None, venue_id=venue_id, name="House Stagebox")
            pe = StagePlotElement(
                job_id=None,
                venue_id=venue_id,
                element_type="speaker_main",
                linked_device_id=dev.id,
            )
            rp = RiggingPoint(job_id=None, venue_id=venue_id, name="House Point")
            pn = PowerNode(job_id=None, venue_id=venue_id, name="House Mains")
            ft = FixtureType(id=uuid4(), job_id=None, venue_id=venue_id, name="House Fixture")
            lf = LightingFixture(
                job_id=None,
                venue_id=venue_id,
                fixture_type="House Light",
                fixture_type_id=ft.id,
                import_batch_id=uuid4(),
            )
            vil = VideoInputList(id=uuid4(), job_id=None, venue_id=venue_id, name="House Cams")
            vi = VideoInput(list_id=vil.id, venue_id=venue_id)
            db.add_all([cl, dev, pe, rp, pn, ft, lf, vil, vi])
            await db.commit()
            cl_id, dev_id, ft_id = cl.id, dev.id, ft.id

        job = (
            await client.post(f"{BASE}/jobs", json={"title": "Rig Job"}, headers=auth_headers)
        ).json()
        assigned = await client.put(
            f"{BASE}/jobs/{job['id']}/venue",
            json={"venue_id": str(venue_id)},
            headers=auth_headers,
        )
        assert assigned.status_code == 200, assigned.text

        async with db_mod.SessionLocal() as db:
            new_cls = (
                (await db.execute(select(ChannelList).where(ChannelList.job_id == UUID(job["id"]))))
                .scalars()
                .all()
            )
            assert len(new_cls) == 1
            assert new_cls[0].id != cl_id
            assert new_cls[0].venue_id is None

            new_devs = (
                (await db.execute(select(AudioDevice).where(AudioDevice.job_id == UUID(job["id"]))))
                .scalars()
                .all()
            )
            assert len(new_devs) == 1
            new_dev = new_devs[0]
            assert new_dev.id != dev_id

            new_pes = (
                (
                    await db.execute(
                        select(StagePlotElement).where(StagePlotElement.job_id == UUID(job["id"]))
                    )
                )
                .scalars()
                .all()
            )
            assert len(new_pes) == 1
            assert new_pes[0].linked_device_id == new_dev.id

            assert (
                await db.execute(select(RiggingPoint).where(RiggingPoint.job_id == UUID(job["id"])))
            ).scalars().first() is not None
            assert (
                await db.execute(select(PowerNode).where(PowerNode.job_id == UUID(job["id"])))
            ).scalars().first() is not None

            new_lf = (
                (
                    await db.execute(
                        select(LightingFixture).where(LightingFixture.job_id == UUID(job["id"]))
                    )
                )
                .scalars()
                .first()
            )
            assert new_lf is not None
            assert new_lf.fixture_type_id != ft_id
            assert new_lf.import_batch_id == lf.import_batch_id

            new_vil = (
                (
                    await db.execute(
                        select(VideoInputList).where(VideoInputList.job_id == UUID(job["id"]))
                    )
                )
                .scalars()
                .first()
            )
            assert new_vil is not None
            new_vi = (
                (await db.execute(select(VideoInput).where(VideoInput.list_id == new_vil.id)))
                .scalars()
                .first()
            )
            assert new_vi is not None
            assert new_vi.list_id == new_vil.id


async def test_base_rig_not_cloned_when_job_already_has_graph(auth_headers):
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        venue = (
            await client.post(
                f"{BASE}/venues", json={**VENUE, "name": "Empty Rig Venue"}, headers=auth_headers
            )
        ).json()
        venue_id = UUID(venue["id"])

        async with db_mod.SessionLocal() as db:
            db.add(AudioDevice(job_id=None, venue_id=venue_id, name="House Stagebox"))
            await db.commit()

        job = (
            await client.post(f"{BASE}/jobs", json={"title": "Prebuilt Job"}, headers=auth_headers)
        ).json()
        async with db_mod.SessionLocal() as db:
            db.add(AudioDevice(job_id=UUID(job["id"]), name="User Device"))
            await db.commit()

        await client.put(
            f"{BASE}/jobs/{job['id']}/venue",
            json={"venue_id": str(venue_id)},
            headers=auth_headers,
        )

        async with db_mod.SessionLocal() as db:
            count = len(
                (await db.execute(select(AudioDevice).where(AudioDevice.job_id == UUID(job["id"]))))
                .scalars()
                .all()
            )
        assert count == 1


async def test_venue_base_rig_crud(auth_headers):
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        venue = (
            await client.post(
                f"{BASE}/venues", json={**VENUE, "name": "Rig Venue"}, headers=auth_headers
            )
        ).json()
        venue_id = venue["id"]

        # 404 for unknown venue
        missing = await client.get(
            f"{BASE}/venues/00000000-0000-0000-0000-000000000000/rig/devices",
            headers=auth_headers,
        )
        assert missing.status_code == 404

        # create
        created = await client.post(
            f"{BASE}/venues/{venue_id}/rig/devices",
            json={"name": "House Stagebox", "device_type": "stagebox"},
            headers=auth_headers,
        )
        assert created.status_code == 201, created.text
        dev_id = created.json()["id"]

        # list
        listed = await client.get(f"{BASE}/venues/{venue_id}/rig/devices", headers=auth_headers)
        assert listed.status_code == 200
        assert len(listed.json()) == 1

        # get by id
        got = await client.get(
            f"{BASE}/venues/{venue_id}/rig/devices/{dev_id}", headers=auth_headers
        )
        assert got.status_code == 200
        assert got.json()["name"] == "House Stagebox"

        # patch (partial)
        patched = await client.patch(
            f"{BASE}/venues/{venue_id}/rig/devices/{dev_id}",
            json={"notes": "Back of house"},
            headers=auth_headers,
        )
        assert patched.status_code == 200, patched.text
        assert patched.json()["notes"] == "Back of house"
        assert patched.json()["name"] == "House Stagebox"

        # ownership: row belongs to the venue, not a job
        async with db_mod.SessionLocal() as db:
            row = (
                (await db.execute(select(AudioDevice).where(AudioDevice.id == UUID(dev_id))))
                .scalars()
                .first()
            )
            assert row.venue_id == UUID(venue_id)
            assert row.job_id is None

        # child entity referencing a venue-owned parent (nested path)
        cl = await client.post(
            f"{BASE}/venues/{venue_id}/rig/channel-lists",
            json={"name": "House Inputs"},
            headers=auth_headers,
        )
        assert cl.status_code == 201, cl.text
        cl_id = cl.json()["id"]
        ch = await client.post(
            f"{BASE}/venues/{venue_id}/rig/channel-lists/{cl_id}/channels",
            json={"channel_number": 1},
            headers=auth_headers,
        )
        assert ch.status_code == 201, ch.text
        assert ch.json()["channel_list_id"] == cl_id
        ch_id = ch.json()["id"]
        got_ch = await client.get(
            f"{BASE}/venues/{venue_id}/rig/channels/{ch_id}", headers=auth_headers
        )
        assert got_ch.status_code == 200
        assert got_ch.json()["channel_list_id"] == cl_id

        # delete
        deleted = await client.delete(
            f"{BASE}/venues/{venue_id}/rig/devices/{dev_id}", headers=auth_headers
        )
        assert deleted.status_code == 204
        gone = await client.get(
            f"{BASE}/venues/{venue_id}/rig/devices/{dev_id}", headers=auth_headers
        )
        assert gone.status_code == 404

        # 404 when row belongs to a different venue
        other = await client.post(
            f"{BASE}/venues", json={**VENUE, "name": "Other Venue"}, headers=auth_headers
        )
        other_id = other.json()["id"]
        cross = await client.get(
            f"{BASE}/venues/{other_id}/rig/devices/{dev_id}", headers=auth_headers
        )
        assert cross.status_code == 404
