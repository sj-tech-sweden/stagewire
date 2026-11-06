import asyncio
from uuid import UUID, uuid4

from httpx import ASGITransport, AsyncClient
from sqlalchemy import select

from app.core import db as db_mod
from app.domains.graph.models import ConnectionEdge, GraphDevice
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


async def test_venue_custom_polygons(auth_headers):
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        poly = [[0, 0], [1000, 0], [1000, 800], [0, 800]]
        stage_poly = [[0, 0], [300, 0], [300, 200], [0, 200]]
        created = await client.post(
            f"{BASE}/venues",
            json={
                **VENUE,
                "footprint_shape": "custom_polygon",
                "stage_shape": "custom_polygon",
                "footprint_polygon": poly,
                "stage_polygon": stage_poly,
            },
            headers=auth_headers,
        )
        assert created.status_code == 201, created.text
        body = created.json()
        assert body["footprint_shape"] == "custom_polygon"
        assert body["stage_shape"] == "custom_polygon"
        assert body["footprint_polygon"] == poly
        assert body["stage_polygon"] == stage_poly

        # A polygon with fewer than three corners is rejected.
        bad = await client.post(
            f"{BASE}/venues",
            json={
                **VENUE,
                "footprint_shape": "custom_polygon",
                "footprint_polygon": [[0, 0], [1, 1]],
            },
            headers=auth_headers,
        )
        assert bad.status_code == 422

        # Patching the polygon is reflected on read.
        vid = body["id"]
        patched = await client.patch(
            f"{BASE}/venues/{vid}",
            json={"footprint_polygon": [[0, 0], [500, 0], [500, 500], [0, 500]]},
            headers=auth_headers,
        )
        assert patched.status_code == 200, patched.text
        assert patched.json()["footprint_polygon"] == [[0, 0], [500, 0], [500, 500], [0, 500]]

        # Assigning the venue copies both polygons onto the job snapshot.
        job = (
            await client.post(f"{BASE}/jobs", json={"title": "Poly Job"}, headers=auth_headers)
        ).json()
        assigned = await client.put(
            f"{BASE}/jobs/{job['id']}/venue", json={"venue_id": vid}, headers=auth_headers
        )
        assert assigned.status_code == 200, assigned.text
        assert assigned.json()["venue_footprint_polygon"] == patched.json()["footprint_polygon"]
        assert assigned.json()["venue_stage_polygon"] == stage_poly
        assert assigned.json()["venue_footprint_shape"] == "custom_polygon"
        assert assigned.json()["venue_stage_shape"] == "custom_polygon"


async def test_base_rig_is_cloned_on_assign(auth_headers):
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        venue = (
            await client.post(
                f"{BASE}/venues", json={**VENUE, "name": "Base Rig Venue"}, headers=auth_headers
            )
        ).json()
        venue_id = UUID(venue["id"])

        # Seed the venue's Standard Base Rig through the graph endpoint.
        dev_a = uuid4()
        dev_b = uuid4()
        edge = uuid4()
        rig = {
            "devices": [
                {
                    "id": str(dev_a),
                    "domain": "audio",
                    "kind": "speaker",
                    "name": "House Stagebox",
                    "attributes": {},
                    "ports": [],
                },
                {
                    "id": str(dev_b),
                    "domain": "audio",
                    "kind": "console",
                    "name": "House Console",
                    "attributes": {},
                    "ports": [],
                },
            ],
            "edges": [
                {
                    "id": str(edge),
                    "signal": "audio",
                    "src_device_id": str(dev_a),
                    "src_port": "out",
                    "dst_device_id": str(dev_b),
                    "dst_port": "in",
                }
            ],
        }
        put = await client.put(f"{BASE}/venues/{venue_id}/graph", json=rig, headers=auth_headers)
        assert put.status_code == 200, put.text
        assert len(put.json()["devices"]) == 2
        assert len(put.json()["edges"]) == 1

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
            # The job got a clone of the rig: same count, fresh ids, venue_id cleared.
            cloned = (
                (await db.execute(select(GraphDevice).where(GraphDevice.job_id == UUID(job["id"]))))
                .scalars()
                .all()
            )
            assert len(cloned) == 2
            assert all(d.venue_id is None for d in cloned)
            assert {d.name for d in cloned} == {"House Stagebox", "House Console"}

            cloned_edges = (
                (
                    await db.execute(
                        select(ConnectionEdge).where(ConnectionEdge.job_id == UUID(job["id"]))
                    )
                )
                .scalars()
                .all()
            )
            assert len(cloned_edges) == 1
            cloned_ids = {d.id for d in cloned}
            assert cloned_edges[0].src_device_id in cloned_ids
            assert cloned_edges[0].dst_device_id in cloned_ids

            # The venue still owns its template rig.
            template = (
                (
                    await db.execute(
                        select(GraphDevice).where(
                            GraphDevice.venue_id == venue_id, GraphDevice.job_id.is_(None)
                        )
                    )
                )
                .scalars()
                .all()
            )
            assert len(template) == 2


async def test_base_rig_not_cloned_when_job_already_has_graph(auth_headers):
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        venue = (
            await client.post(
                f"{BASE}/venues", json={**VENUE, "name": "Empty Rig Venue"}, headers=auth_headers
            )
        ).json()
        venue_id = UUID(venue["id"])

        # Venue carries a base-rig device.
        dev = uuid4()
        await client.put(
            f"{BASE}/venues/{venue_id}/graph",
            json={
                "devices": [
                    {
                        "id": str(dev),
                        "domain": "audio",
                        "kind": "speaker",
                        "name": "House Stagebox",
                        "attributes": {},
                        "ports": [],
                    }
                ],
                "edges": [],
            },
            headers=auth_headers,
        )

        job = (
            await client.post(f"{BASE}/jobs", json={"title": "Prebuilt Job"}, headers=auth_headers)
        ).json()
        async with db_mod.SessionLocal() as db:
            # A job that already carries its own graph must not be overwritten by the rig.
            db.add(
                GraphDevice(
                    job_id=UUID(job["id"]), domain="audio", kind="console", name="User Device"
                )
            )
            await db.commit()

        await client.put(
            f"{BASE}/jobs/{job['id']}/venue",
            json={"venue_id": str(venue_id)},
            headers=auth_headers,
        )

        async with db_mod.SessionLocal() as db:
            count = len(
                (await db.execute(select(GraphDevice).where(GraphDevice.job_id == UUID(job["id"]))))
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
            f"{BASE}/venues/00000000-0000-0000-0000-000000000000/graph", headers=auth_headers
        )
        assert missing.status_code == 404

        # Empty rig initially
        empty = await client.get(f"{BASE}/venues/{venue_id}/graph", headers=auth_headers)
        assert empty.status_code == 200
        assert empty.json()["devices"] == []
        assert empty.json()["edges"] == []

        # PUT a rig with two devices + one edge
        dev_a = uuid4()
        dev_b = uuid4()
        edge = uuid4()
        rig = {
            "devices": [
                {
                    "id": str(dev_a),
                    "domain": "audio",
                    "kind": "speaker",
                    "name": "A",
                    "attributes": {},
                    "ports": [],
                },
                {
                    "id": str(dev_b),
                    "domain": "audio",
                    "kind": "speaker",
                    "name": "B",
                    "attributes": {},
                    "ports": [],
                },
            ],
            "edges": [
                {
                    "id": str(edge),
                    "signal": "audio",
                    "src_device_id": str(dev_a),
                    "src_port": "out",
                    "dst_device_id": str(dev_b),
                    "dst_port": "in",
                }
            ],
        }
        created = await client.put(
            f"{BASE}/venues/{venue_id}/graph", json=rig, headers=auth_headers
        )
        assert created.status_code == 200, created.text
        assert len(created.json()["devices"]) == 2
        assert len(created.json()["edges"]) == 1

        # Replacing keeps ids stable and discards removed devices
        rig2 = {
            "devices": [
                {
                    "id": str(dev_a),
                    "domain": "audio",
                    "kind": "speaker",
                    "name": "A renamed",
                    "attributes": {},
                    "ports": [],
                }
            ],
            "edges": [],
        }
        replaced = await client.put(
            f"{BASE}/venues/{venue_id}/graph", json=rig2, headers=auth_headers
        )
        assert replaced.status_code == 200, replaced.text
        assert len(replaced.json()["devices"]) == 1
        assert replaced.json()["devices"][0]["name"] == "A renamed"

        # Persistence: the row is venue-owned with a null job_id
        async with db_mod.SessionLocal() as db:
            row = (
                (await db.execute(select(GraphDevice).where(GraphDevice.id == dev_a)))
                .scalars()
                .first()
            )
            assert row is not None
            assert row.venue_id == UUID(venue_id)
            assert row.job_id is None


async def test_venue_cable_plan_round_trip(auth_headers):
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        venue = (
            await client.post(
                f"{BASE}/venues", json={**VENUE, "name": "Cable Plan Venue"}, headers=auth_headers
            )
        ).json()
        venue_id = venue["id"]

        # A new venue starts with an empty (default {}) cable plan.
        fresh = await client.get(f"{BASE}/venues/{venue_id}", headers=auth_headers)
        assert fresh.status_code == 200, fresh.text
        assert fresh.json()["cable_plan"] == {}

        # PATCH a realistic plan: fixed cableways (raceways) plus routing settings and overrides.
        plan = {
            "cableways": [
                {"id": str(uuid4()), "points": [[0, 0], [100, 0], [100, 50]]},
            ],
            "settings": {"default_route_mode": "auto", "bundle_threshold_cm": 30},
            "routes": {
                "audio:1->2": {"mode": "manual", "waypoints": [[10, 10]], "hidden": False},
            },
        }
        patched = await client.patch(
            f"{BASE}/venues/{venue_id}", json={"cable_plan": plan}, headers=auth_headers
        )
        assert patched.status_code == 200, patched.text
        assert patched.json()["cable_plan"] == plan

        # The value is persisted and returned on a subsequent GET (round-trip).
        again = await client.get(f"{BASE}/venues/{venue_id}", headers=auth_headers)
        assert again.status_code == 200, again.text
        assert again.json()["cable_plan"] == plan

        # PATCHing other fields leaves cable_plan untouched.
        updated = await client.patch(
            f"{BASE}/venues/{venue_id}",
            json={"notes": "Re-racked the trays"},
            headers=auth_headers,
        )
        assert updated.status_code == 200, updated.text
        assert updated.json()["cable_plan"] == plan
        assert updated.json()["notes"] == "Re-racked the trays"

        # A null plan resets to the default.
        cleared = await client.patch(
            f"{BASE}/venues/{venue_id}", json={"cable_plan": None}, headers=auth_headers
        )
        assert cleared.status_code == 200, cleared.text
        assert cleared.json()["cable_plan"] == {}


async def test_propagate_pushes_base_rig_into_jobs(auth_headers):
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        venue = (
            await client.post(
                f"{BASE}/venues", json={**VENUE, "name": "Rig Prop Venue"}, headers=auth_headers
            )
        ).json()
        vid = venue["id"]

        # A job assigned while the venue rig is still empty starts with no devices.
        job = (
            await client.post(f"{BASE}/jobs", json={"title": "Rig Job"}, headers=auth_headers)
        ).json()
        await client.put(
            f"{BASE}/jobs/{job['id']}/venue", json={"venue_id": vid}, headers=auth_headers
        )
        empty = (await client.get(f"{BASE}/jobs/{job['id']}/graph", headers=auth_headers)).json()
        assert empty["devices"] == []

        # Seed two venue rig devices plus an edge between them.
        dev_a, dev_b = uuid4(), uuid4()
        rig = {
            "devices": [
                {
                    "id": str(dev_a),
                    "domain": "audio",
                    "kind": "speaker",
                    "name": "House Speaker",
                    "attributes": {},
                    "ports": [],
                },
                {
                    "id": str(dev_b),
                    "domain": "audio",
                    "kind": "console",
                    "name": "House Console",
                    "attributes": {},
                    "ports": [],
                },
            ],
            "edges": [
                {
                    "id": str(uuid4()),
                    "signal": "audio",
                    "src_device_id": str(dev_a),
                    "src_port": "out",
                    "dst_device_id": str(dev_b),
                    "dst_port": "in",
                }
            ],
        }
        put = await client.put(f"{BASE}/venues/{vid}/graph", json=rig, headers=auth_headers)
        assert put.status_code == 200, put.text

        # Propagate: the (still empty) job receives the full rig.
        prop = await client.post(
            f"{BASE}/venues/{vid}/propagate", json={"scope": "all"}, headers=auth_headers
        )
        assert prop.status_code == 200, prop.text
        assert prop.json()["updated"] == 1
        job_graph = (
            await client.get(f"{BASE}/jobs/{job['id']}/graph", headers=auth_headers)
        ).json()
        assert {d["name"] for d in job_graph["devices"]} == {"House Speaker", "House Console"}
        assert len(job_graph["edges"]) == 1

        # Add a third venue device and re-propagate: the job gains it but keeps the first two
        # (additive — matching devices are skipped so there are no duplicates, and existing ones are
        # never overwritten).
        dev_c = uuid4()
        await client.put(
            f"{BASE}/venues/{vid}/graph",
            json={
                "devices": rig["devices"]
                + [
                    {
                        "id": str(dev_c),
                        "domain": "lighting",
                        "kind": "dimmer",
                        "name": "House Dimmer",
                        "attributes": {},
                        "ports": [],
                    }
                ],
                "edges": rig["edges"],
            },
            headers=auth_headers,
        )
        prop2 = await client.post(
            f"{BASE}/venues/{vid}/propagate", json={"scope": "all"}, headers=auth_headers
        )
        assert prop2.status_code == 200, prop2.text
        job_graph2 = (
            await client.get(f"{BASE}/jobs/{job['id']}/graph", headers=auth_headers)
        ).json()
        names = {d["name"] for d in job_graph2["devices"]}
        assert names == {"House Speaker", "House Console", "House Dimmer"}
        assert sum(1 for d in job_graph2["devices"] if d["name"] == "House Speaker") == 1

        # Editing a job device and re-propagating must NOT overwrite it (the rename survives).
        speaker = next(d for d in job_graph2["devices"] if d["name"] == "House Speaker")
        renamed = await client.patch(
            f"{BASE}/jobs/{job['id']}/graph/devices/{speaker['id']}",
            json={"name": "Renamed Speaker", "expected_revision": speaker["revision"]},
            headers=auth_headers,
        )
        assert renamed.status_code == 200, renamed.text
        await client.post(
            f"{BASE}/venues/{vid}/propagate", json={"scope": "all"}, headers=auth_headers
        )
        final = (await client.get(f"{BASE}/jobs/{job['id']}/graph", headers=auth_headers)).json()
        assert any(d["name"] == "Renamed Speaker" for d in final["devices"])
