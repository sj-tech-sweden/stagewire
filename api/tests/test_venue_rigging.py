import pytest
from httpx import ASGITransport, AsyncClient

from app.main import app

BASE = "/api/v1"


async def _venue_with_power(client, h):
    """A venue with a one-phase power group and one outlet on it, plus a standalone outlet."""
    venue = (await client.post(f"{BASE}/venues", json={"name": "Hall"}, headers=h)).json()
    venue_id = venue["id"]
    group = (
        await client.post(
            f"{BASE}/venues/{venue_id}/power-groups",
            json={"name": "Stage left", "rating_amps": 16, "phases": 1},
            headers=h,
        )
    ).json()
    outlet = (
        await client.post(
            f"{BASE}/venues/{venue_id}/power-outlets",
            json={"name": "SL1", "connector": "schuko", "group_id": group["id"]},
            headers=h,
        )
    ).json()
    # a second outlet on the same group so its source node has capacity for an extra feed
    await client.post(
        f"{BASE}/venues/{venue_id}/power-outlets",
        json={"name": "SL2", "connector": "schuko", "group_id": group["id"]},
        headers=h,
    )
    single = (
        await client.post(
            f"{BASE}/venues/{venue_id}/power-outlets",
            json={"name": "Wall", "connector": "cee16", "rating_amps": 16},
            headers=h,
        )
    ).json()
    return venue_id, group, outlet, single


@pytest.mark.asyncio
async def test_venue_rigging_and_power_use_the_graph_api_and_are_isolated_from_jobs(auth_headers):
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        h = auth_headers
        venue_id, _group, outlet, single = await _venue_with_power(client, h)
        g = f"{BASE}/venues/{venue_id}/graph"

        # A separate job must not share the venue's rigging/power rows.
        job_id = (await client.post(f"{BASE}/jobs", json={"title": "Other"}, headers=h)).json()[
            "id"
        ]

        # --- rigging points -------------------------------------------------
        point = (
            await client.post(
                f"{g}/rigging-points",
                json={"name": "FOH truss", "weight_capacity_kg": 100},
                headers=h,
            )
        ).json()
        assert point["kind"] == "rigging_point" and point["domain"] == "rigging"
        assert point["attributes"]["weight_capacity_kg"] == 100

        # --- venue power: an outlet becomes a source node -------------------
        source = (
            await client.post(f"{g}/venue-power/outlets/{outlet['id']}/source", headers=h)
        ).json()
        node = source["node"]
        assert node["kind"] == "source" and node["name"] == "Stage left"
        assert source["connector"] == "schuko"

        # --- a power node hung from the source ------------------------------
        distro = (
            await client.post(
                f"{g}/power-nodes",
                json={
                    "name": "Distro",
                    "kind": "distro",
                    "parent_id": node["id"],
                    "feed_connector": "schuko",
                    "outputs": [{"connector": "schuko", "count": 4}],
                },
                headers=h,
            )
        ).json()
        assert distro["kind"] == "distro"
        # The power-node *list* keys nodes by their legacy power id, distinct from the graph host
        # id the graph API returns, so match rows by name and read parent/ids from the list.
        nodes = (await client.get(f"{BASE}/venues/{venue_id}/power-nodes", headers=h)).json()
        source_row = next(n for n in nodes if n["name"] == "Stage left")
        distro_row = next(n for n in nodes if n["name"] == "Distro")
        assert distro_row["parent_id"] == source_row["id"]

        # --- an extra (merged) feed onto the distro ------------------------
        feed = await client.post(
            f"{g}/power-nodes/{distro['id']}/feeds",
            json={"parent_id": node["id"], "feed_connector": "schuko"},
            headers=h,
        )
        assert feed.status_code == 201, feed.text

        # --- re-hang the distro under a second source (PUT .../parent) -----
        src2 = (
            await client.post(f"{g}/venue-power/outlets/{single['id']}/source", headers=h)
        ).json()["node"]
        moved = await client.put(
            f"{g}/power-nodes/{distro['id']}/parent",
            json={"parent_id": src2["id"], "feed_connector": "cee16"},
            headers=h,
        )
        assert moved.status_code == 200, moved.text
        nodes = (await client.get(f"{BASE}/venues/{venue_id}/power-nodes", headers=h)).json()
        src2_row = next(n for n in nodes if n["name"] == "Wall")
        distro_row = next(n for n in nodes if n["name"] == "Distro")
        assert distro_row["parent_id"] == src2_row["id"]

        # --- an audio device + load assignment (power + rigging) ----------
        gear = (
            await client.post(
                f"{g}/audio-devices",
                json={"name": "Amp", "device_type": "other", "power_watts": 600, "weight_kg": 20},
                headers=h,
            )
        ).json()
        loaded = await client.put(
            f"{g}/loads/{gear['id']}",
            json={
                "power_node_id": distro["id"],
                "power_connector": "schuko",
                "rigging_point_id": point["id"],
            },
            headers=h,
        )
        assert loaded.status_code == 200, loaded.text
        # Both ids are stored as their graph host id (the `GraphDevice` id), not the legacy power
        # id; the summary remaps node ids and load power_node_id onto the same graph host ids so the
        # frontend sees one consistent scheme. The job path stores the identical form.
        assert loaded.json()["attributes"]["rigging_point_id"] == point["id"]
        assert loaded.json()["attributes"]["power_node_id"] == distro["id"]

        # --- the summary reflects the venue rigging -----------------------
        summary = (await client.get(f"{g}/rigging/summary", headers=h)).json()
        assert any(p["name"] == "FOH truss" for p in summary["points"])
        assert any(n["name"] == "Distro" for n in summary["nodes"])
        assert any(load["kind"] == "device" for load in summary["loads"])

        # --- isolation from the separate job -------------------------------
        assert (await client.get(f"{BASE}/jobs/{job_id}/power-nodes", headers=h)).json() == []
        assert (await client.get(f"{BASE}/jobs/{job_id}/rigging-points", headers=h)).json() == []
        job_summary = (
            await client.get(f"{BASE}/jobs/{job_id}/graph/rigging/summary", headers=h)
        ).json()
        assert job_summary["points"] == [] and job_summary["nodes"] == []


@pytest.mark.asyncio
async def test_venue_rigging_and_power_are_isolated_across_venues(auth_headers):
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        h = auth_headers
        venue_a, _ga, outlet_a, _sa = await _venue_with_power(client, h)
        venue_b, _gb, outlet_b, _sb = await _venue_with_power(client, h)
        ga = f"{BASE}/venues/{venue_a}/graph"
        gb = f"{BASE}/venues/{venue_b}/graph"

        pa = (await client.post(f"{ga}/rigging-points", json={"name": "Truss A"}, headers=h)).json()
        await client.post(f"{ga}/venue-power/outlets/{outlet_a['id']}/source", headers=h)

        # venue B sees neither the point nor the power node of venue A
        assert (await client.get(f"{BASE}/venues/{venue_b}/rigging-points", headers=h)).json() == []
        summary_b = (await client.get(f"{gb}/rigging/summary", headers=h)).json()
        assert summary_b["points"] == [] and summary_b["nodes"] == []
        # and venue A's point is its own
        summary_a = (await client.get(f"{ga}/rigging/summary", headers=h)).json()
        assert summary_a["points"][0]["id"] == pa["id"]


@pytest.mark.asyncio
async def test_job_rigging_and_power_still_use_the_same_graph_api(auth_headers):
    """The job path is byte-identical: same handlers, just job_id set and venue_id None."""
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        h = auth_headers
        job_id = (await client.post(f"{BASE}/jobs", json={"title": "Rig"}, headers=h)).json()["id"]
        g = f"{BASE}/jobs/{job_id}/graph"

        source = (
            await client.post(
                f"{g}/power-nodes",
                json={
                    "name": "Mains",
                    "kind": "source",
                    "feed_connector": "cee63_3p",
                    "rating_amps": 63,
                    "outputs": [{"connector": "cee32_3p", "count": 2}],
                },
                headers=h,
            )
        ).json()
        assert source["kind"] == "source"
        distro = (
            await client.post(
                f"{g}/power-nodes",
                json={
                    "name": "Distro",
                    "kind": "distro",
                    "parent_id": source["id"],
                    "feed_connector": "cee32_3p",
                    "outputs": [{"connector": "schuko", "count": 4}],
                },
                headers=h,
            )
        ).json()
        point = (
            await client.post(f"{g}/rigging-points", json={"name": "FOH truss"}, headers=h)
        ).json()
        gear = (
            await client.post(
                f"{g}/audio-devices",
                json={"name": "Amp", "device_type": "other", "power_watts": 800},
                headers=h,
            )
        ).json()
        res = await client.put(
            f"{g}/loads/{gear['id']}",
            json={
                "power_node_id": distro["id"],
                "power_connector": "schuko",
                "rigging_point_id": point["id"],
            },
            headers=h,
        )
        assert res.status_code == 200, res.text
        summary = (await client.get(f"{g}/rigging/summary", headers=h)).json()
        assert any(n["name"] == "Mains" for n in summary["nodes"])
        assert any(p["name"] == "FOH truss" for p in summary["points"])


@pytest.mark.asyncio
async def test_venue_graph_device_and_edge_crud_and_isolation(auth_headers):
    """A venue's canvas reuses the job graph CRUD (create/update/delete device & edge) and stays
    isolated from jobs — full unification, not a parallel venue-only API."""
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        h = auth_headers
        venue_id, _ga, _oa, _sa = await _venue_with_power(client, h)
        g = f"{BASE}/venues/{venue_id}/graph"

        # --- create devices through the batch endpoint the workspace canvas uses -----------
        created = (
            await client.post(
                f"{g}/devices/batch",
                json=[
                    {
                        "domain": "audio",
                        "kind": "speaker",
                        "name": "L",
                        "canvas_x_cm": 0,
                        "canvas_y_cm": 0,
                        "attributes": {},
                        "ports": [
                            {
                                "id": "out",
                                "direction": "out",
                                "signal": "audio",
                                "connector": "xlr",
                                "channels": 1,
                                "max_connections": 1,
                            }
                        ],
                    },
                    {
                        "domain": "audio",
                        "kind": "speaker",
                        "name": "R",
                        "canvas_x_cm": 10,
                        "canvas_y_cm": 0,
                        "attributes": {},
                        "ports": [
                            {
                                "id": "in",
                                "direction": "in",
                                "signal": "audio",
                                "connector": "xlr",
                                "channels": 1,
                                "max_connections": 1,
                            }
                        ],
                    },
                ],
                headers=h,
            )
        ).json()
        assert len(created) == 2
        left, right = created[0], created[1]

        # --- PATCH a device: rename and set a power drawing attribute ---------------------
        patched_resp = await client.patch(
            f"{g}/devices/{left['id']}",
            json={
                "name": "Left",
                "attributes": {"power_w": 300},
                "expected_revision": left["revision"],
            },
            headers=h,
        )
        patched = patched_resp.json()
        assert patched["name"] == "Left"
        assert patched["attributes"]["power_w"] == 300

        # --- connect them with an audio edge, then edit and delete it --------------------
        edge_resp = await client.post(
            f"{g}/edges",
            json={
                "signal": "audio",
                "src_device_id": left["id"],
                "src_port": "out",
                "dst_device_id": right["id"],
                "dst_port": "in",
                "channels": 1,
                "phase": None,
            },
            headers=h,
        )
        edge = edge_resp.json()
        assert edge["signal"] == "audio"
        edge_patched = (
            await client.patch(
                f"{g}/edges/{edge['id']}",
                json={"cable_label": "XLR", "expected_revision": edge["revision"]},
                headers=h,
            )
        ).json()
        assert edge_patched["cable_label"] == "XLR"
        del_edge = await client.delete(
            f"{g}/edges/{edge['id']}",
            params={"expected_revision": edge_patched["revision"]},
            headers=h,
        )
        assert del_edge.status_code == 204

        # --- delete a device --------------------------------------------------------------
        del_dev = await client.delete(
            f"{g}/devices/{right['id']}", params={"expected_revision": right["revision"]}, headers=h
        )
        assert del_dev.status_code == 204

        # --- GET graph reflects the deletions --------------------------------------------
        graph = (await client.get(g, headers=h)).json()
        ids = {d["id"] for d in graph["devices"]}
        assert left["id"] in ids and right["id"] not in ids
        assert all(e["id"] != edge["id"] for e in graph["edges"])

        # --- isolation: a job shares none of the venue's graph rows -----------------------
        job_id = (await client.post(f"{BASE}/jobs", json={"title": "Other"}, headers=h)).json()[
            "id"
        ]
        job_graph = (await client.get(f"{BASE}/jobs/{job_id}/graph", headers=h)).json()
        assert job_graph["devices"] == [] and job_graph["edges"] == []
