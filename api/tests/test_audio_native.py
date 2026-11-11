"""Channel lists, channels, outputs and patch points on the graph: no legacy tables behind them.

The legacy endpoints and the graph endpoints write the same nodes; the patch edges are drawn from
the points, and the ids other things hold (plot links, a device's sound list) stay valid."""

from uuid import UUID

import pytest
from httpx import ASGITransport, AsyncClient

from app.main import app

BASE = "/api/v1"


async def _setup(client, h):
    job_id = (await client.post(f"{BASE}/jobs", json={"title": "Audio"}, headers=h)).json()["id"]
    api = f"{BASE}/jobs/{job_id}"

    async def post(path, body):
        res = await client.post(f"{api}/{path}", json=body, headers=h)
        assert res.status_code == 201, res.text
        return res.json()

    lst = await post("channel-lists", {"name": "FOH"})
    ch = await post(
        f"channel-lists/{lst['id']}/channels", {"channel_number": 1, "source_label": "Vox"}
    )
    box = await post("devices", {"name": "Stagebox", "device_type": "analog_stagebox"})
    desk = await post("devices", {"name": "Desk", "device_type": "mixer"})
    return job_id, api, post, lst, ch, box, desk


async def _graph(client, h, api):
    return (await client.get(f"{api}/graph", headers=h)).json()


@pytest.mark.asyncio
async def test_lists_channels_and_points_are_nodes_and_their_edges_follow_the_points(auth_headers):
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        h = auth_headers
        job_id, api, post, lst, ch, box, desk = await _setup(client, h)
        graph = await _graph(client, h, api)
        nodes = {d["id"]: d for d in graph["devices"]}
        # a new row's id is its node id; there is no legacy ref behind the node
        assert nodes[lst["id"]]["kind"] == "channel_list" and nodes[lst["id"]]["legacy_ref"] is None
        node = nodes[ch["id"]]
        assert (node["kind"], node["name"], node["position"], node["legacy_ref"]) == (
            "channel",
            "Vox",
            1,
            None,
        )
        assert node["attributes"]["list_id"] == lst["id"] and node["attributes"]["points"] == []

        first = await post(
            f"channels/{ch['id']}/patch-points", {"device_id": box["id"], "connector": "XLR"}
        )
        second = await post(
            f"channels/{ch['id']}/patch-points", {"device_id": desk["id"], "position": 1}
        )
        edges = [e for e in (await _graph(client, h, api))["edges"] if e["signal"] == "audio"]
        assert [
            e["attributes"]["point_id"]
            for e in sorted(edges, key=lambda e: e["attributes"]["position"])
        ] == [
            first["id"],
            second["id"],
        ]
        # a point edit is the point's own revision; a stale one is a conflict
        res = await client.patch(
            f"{api}/channels/{ch['id']}/patch-points/{first['id']}",
            json={"patch_label": "In 1", "expected_revision": first["revision"]},
            headers=h,
        )
        assert res.status_code == 200 and res.json()["revision"] == first["revision"] + 1
        stale = await client.patch(
            f"{api}/channels/{ch['id']}/patch-points/{first['id']}",
            json={"patch_label": "again", "expected_revision": first["revision"]},
            headers=h,
        )
        assert stale.status_code == 409
        edge = next(
            e
            for e in (await _graph(client, h, api))["edges"]
            if e["attributes"]["point_id"] == first["id"]
        )
        assert edge["attributes"]["patch_label"] == "In 1"

        # a device with patch points cannot be removed; without them it can
        busy = await client.delete(f"{api}/devices/{box['id']}", headers=h)
        assert busy.status_code == 409
        res = await client.delete(
            f"{api}/channels/{ch['id']}/patch-points/{first['id']}",
            params={"expected_revision": 2},
            headers=h,
        )
        assert res.status_code == 204
        assert (await client.delete(f"{api}/devices/{box['id']}", headers=h)).status_code == 204


@pytest.mark.asyncio
async def test_a_channel_is_a_two_way_node_and_a_non_forced_edge_can_end_on_it(auth_headers):
    """A channel is the true endpoint of the signal chain: it exposes both an `in` port (where a
    source such as a mic or a digital stagebox terminates) and the existing `out` port (toward the
    mix). Because the `in` port now exists, a normal (non-forced) audio edge can land on a channel
    node rather than needing the legacy force-bypass used by the mic auto-connect path."""
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        h = auth_headers
        job_id, api, post, lst, ch, box, desk = await _setup(client, h)
        # a second channel so we can patch one channel's output into another's input
        ch2 = await post(
            f"channel-lists/{lst['id']}/channels",
            {"channel_number": 2, "source_label": "Gtr"},
        )
        nodes = {d["id"]: d for d in (await _graph(client, h, api))["devices"]}
        chan = nodes[ch["id"]]
        # the channel node carries both an input and an output port
        port_ids = {p["id"] for p in chan["ports"]}
        assert {"in", "out"} <= port_ids
        assert {p["direction"] for p in chan["ports"] if p["id"] == "in"} == {"in"}
        assert {p["direction"] for p in chan["ports"] if p["id"] == "out"} == {"out"}

        # a non-forced edge that terminates on the channel node's `in` port is accepted
        res = await client.post(
            f"{api}/graph/edges",
            json={
                "signal": "audio",
                "src_device_id": ch["id"],
                "src_port": "out",
                "dst_device_id": ch2["id"],
                "dst_port": "in",
                "channels": 1,
            },
            headers=h,
        )
        assert res.status_code == 201, res.text
        edge = res.json()
        assert edge["src_device_id"] == ch["id"] and edge["src_port"] == "out"
        assert edge["dst_device_id"] == ch2["id"] and edge["dst_port"] == "in"


@pytest.mark.asyncio
async def test_a_legacy_channel_missing_the_in_port_is_normalised_and_still_accepts_an_edge(
    auth_headers,
):
    """Channels created before the `in` port was introduced only stored an `out` port. The `in`
    port must be derived at read/validation time (not trusted from the stored column), so such a
    channel still validates as a connection endpoint and shows both ports in the graph."""
    from app.core import db as db_mod
    from app.domains.graph.models import GraphDevice

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        h = auth_headers
        job_id, api, post, lst, ch, box, desk = await _setup(client, h)
        # a second channel (fresh, has both ports) to use as the source of the edge
        ch2 = await post(
            f"channel-lists/{lst['id']}/channels",
            {"channel_number": 2, "source_label": "Gtr"},
        )
        # simulate legacy data: strip the channel's stored `in` port
        async with db_mod.SessionLocal() as db:
            node = await db.get(GraphDevice, UUID(ch["id"]))
            node.ports = [p for p in node.ports if p["id"] != "in"]
            await db.commit()

        # the graph read derives the missing `in` port
        nodes = {d["id"]: d for d in (await _graph(client, h, api))["devices"]}
        assert {p["id"] for p in nodes[ch["id"]]["ports"]} == {"in", "out"}

        # and a non-forced edge into the channel's `in` is accepted despite the stale storage
        res = await client.post(
            f"{api}/graph/edges",
            json={
                "signal": "audio",
                "src_device_id": ch2["id"],
                "src_port": "out",
                "dst_device_id": ch["id"],
                "dst_port": "in",
                "channels": 1,
            },
            headers=h,
        )
        assert res.status_code == 201, res.text


@pytest.mark.asyncio
async def test_an_output_chain_branches_and_deleting_a_point_hands_its_children_up(auth_headers):
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        h = auth_headers
        job_id, api, post, lst, ch, console, amp = await _setup(client, h)
        await post("devices", {"name": "Spk", "device_type": "speaker"})
        out = await post(f"channel-lists/{lst['id']}/outputs", {"name": "Mon 1"})
        g = f"{api}/graph"
        nodes = {d["name"]: d for d in (await _graph(client, h, api))["devices"]}
        res = await client.put(
            f"{g}/outputs/{out['id']}/chain",
            json={
                "steps": [
                    {"device_id": nodes["Desk"]["id"]},
                    {"device_id": nodes["Stagebox"]["id"], "parent_index": 0},
                    {"device_id": nodes["Spk"]["id"], "parent_index": 1, "parallel": True},
                ]
            },
            headers=h,
        )
        assert res.status_code == 200, res.text
        edges = (await _graph(client, h, api))["edges"]
        names = {d["id"]: d["name"] for d in (await _graph(client, h, api))["devices"]}
        path = {(names[e["src_device_id"]], names[e["dst_device_id"]]) for e in edges}
        assert path == {("Desk", "Mon 1"), ("Mon 1", "Stagebox"), ("Stagebox", "Spk")}
        legacy = (await client.get(f"{api}/channel-lists", headers=h)).json()[0]["outputs"][0]
        assert [p["parallel"] for p in legacy["points"]] == [False, False, True]
        assert legacy["points"][2]["parent_id"] == legacy["points"][1]["id"]

        # deleting the middle edge removes its point; the speaker moves up to the bus
        middle = next(e for e in edges if names[e["dst_device_id"]] == "Stagebox")
        res = await client.delete(
            f"{g}/edges/{middle['id']}", params={"expected_revision": middle["revision"]}, headers=h
        )
        assert res.status_code == 204
        legacy = (await client.get(f"{api}/channel-lists", headers=h)).json()[0]["outputs"][0]
        assert len(legacy["points"]) == 2
        assert legacy["points"][1]["parent_id"] == legacy["points"][0]["id"]


@pytest.mark.asyncio
async def test_deleting_a_list_takes_its_rows_and_clears_what_pointed_at_it(auth_headers):
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        h = auth_headers
        job_id, api, post, lst, ch, box, desk = await _setup(client, h)
        await post(f"channels/{ch['id']}/patch-points", {"device_id": box["id"]})
        await post(f"channel-lists/{lst['id']}/outputs", {"name": "Main"})
        res = await client.patch(
            f"{api}/devices/{desk['id']}", json={"sound_list_id": lst["id"]}, headers=h
        )
        assert res.status_code == 200, res.text
        el = (
            await client.post(
                f"{api}/plot-elements",
                json={"element_type": "microphone", "linked_channel_id": ch["id"]},
                headers=h,
            )
        ).json()

        # the element's link goes when the channel does (what the foreign key's SET NULL did)
        fresh = (await client.get(f"{api}/channel-lists", headers=h)).json()[0]["channels"][0]
        res = await client.delete(
            f"{api}/channels/{ch['id']}", params={"expected_revision": fresh["revision"]}, headers=h
        )
        assert res.status_code == 204, res.text
        rows = (await client.get(f"{api}/plot-elements", headers=h)).json()
        assert next(r for r in rows if r["id"] == el["id"])["linked_channel_id"] is None

        assert (
            await client.delete(f"{api}/channel-lists/{lst['id']}", headers=h)
        ).status_code == 204
        graph = await _graph(client, h, api)
        assert not [
            d for d in graph["devices"] if d["kind"] in ("channel_list", "channel", "output")
        ]
        assert not [e for e in graph["edges"] if e["signal"] == "audio"]
        devices = (await client.get(f"{api}/devices", headers=h)).json()
        assert next(d for d in devices if d["id"] == desk["id"])["sound_list_id"] is None


@pytest.mark.asyncio
async def test_a_graph_rename_is_the_label_and_a_position_is_the_number(auth_headers):
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        h = auth_headers
        job_id, api, post, lst, ch, box, desk = await _setup(client, h)
        node = {d["id"]: d for d in (await _graph(client, h, api))["devices"]}[ch["id"]]
        res = await client.patch(
            f"{api}/graph/devices/{node['id']}",
            json={
                "name": "Lead vox",
                "position": 7,
                "attributes": {"phantom_power": None},
                "expected_revision": node["revision"],
            },
            headers=h,
        )
        assert res.status_code == 200, res.text
        row = (await client.get(f"{api}/channel-lists", headers=h)).json()[0]["channels"][0]
        assert (row["source_label"], row["channel_number"], row["phantom_power"]) == (
            "Lead vox",
            7,
            False,  # a null keeps the old column's default
        )
        assert res.json()["name"] == "Lead vox" and res.json()["position"] == 7
