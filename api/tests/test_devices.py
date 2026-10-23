from httpx import ASGITransport, AsyncClient

from app.main import app

BASE = "/api/v1"


async def test_device_crud_and_linking(auth_headers):
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        job = await client.post(
            f"{BASE}/jobs", json={"title": "DevJob", "venue_name": "V"}, headers=auth_headers
        )
        assert job.status_code == 201, job.text
        job_id = job.json()["id"]

        # Create a device (whole physical box).
        dev = await client.post(
            f"{BASE}/jobs/{job_id}/devices",
            json={"name": "Stagebox A", "device_type": "digital_stagebox"},
            headers=auth_headers,
        )
        assert dev.status_code == 201, dev.text
        dev_id = dev.json()["id"]
        assert dev.json()["name"] == "Stagebox A"
        assert dev.json()["patch_point_count"] == 0

        # Create a channel list, then a channel, then a patch point named like
        # the device, and finally group that patch point under the device.
        cl = await client.post(
            f"{BASE}/jobs/{job_id}/channel-lists",
            json={"name": "Inputs"},
            headers=auth_headers,
        )
        assert cl.status_code == 201, cl.text
        list_id = cl.json()["id"]

        ch = await client.post(
            f"{BASE}/jobs/{job_id}/channel-lists/{list_id}/channels",
            json={"channel_number": 1, "source_label": "Kick"},
            headers=auth_headers,
        )
        assert ch.status_code == 201, ch.text
        channel_id = ch.json()["id"]

        no_device = await client.post(
            f"{BASE}/jobs/{job_id}/channels/{channel_id}/patch-points",
            json={"position": 0, "name": "Stagebox A"},
            headers=auth_headers,
        )
        assert no_device.status_code == 422, no_device.text

        pt = await client.post(
            f"{BASE}/jobs/{job_id}/channels/{channel_id}/patch-points",
            json={"position": 0, "point_type": "mixer", "name": "Stagebox A", "device_id": dev_id},
            headers=auth_headers,
        )
        assert pt.status_code == 201, pt.text
        assert pt.json()["point_type"] == "digital_stagebox"
        point_id = pt.json()["id"]

        unlink = await client.patch(
            f"{BASE}/jobs/{job_id}/channels/{channel_id}/patch-points/{point_id}",
            json={"device_id": None},
            headers=auth_headers,
        )
        assert unlink.status_code == 422, unlink.text

        upd = await client.patch(
            f"{BASE}/jobs/{job_id}/channels/{channel_id}/patch-points/{point_id}",
            json={"device_id": dev_id},
            headers=auth_headers,
        )
        assert upd.status_code == 200, upd.text

        lst = await client.get(f"{BASE}/jobs/{job_id}/devices", headers=auth_headers)
        assert lst.status_code == 200
        assert lst.json()[0]["patch_point_count"] == 1

        # Link a stage-plot element to the whole device.
        el = await client.post(
            f"{BASE}/jobs/{job_id}/plot-elements",
            json={
                "element_type": "instrument",
                "linked_device_id": dev_id,
                "position_x": 0,
                "position_y": 0,
            },
            headers=auth_headers,
        )
        assert el.status_code == 201, el.text
        assert el.json()["linked_device_id"] == dev_id

        # Update + delete the device (patch point linkage must be released).
        u = await client.patch(
            f"{BASE}/jobs/{job_id}/devices/{dev_id}",
            json={"name": "Stagebox B"},
            headers=auth_headers,
        )
        assert u.status_code == 200 and u.json()["name"] == "Stagebox B"

        blocked = await client.delete(
            f"{BASE}/jobs/{job_id}/devices/{dev_id}", headers=auth_headers
        )
        assert blocked.status_code == 409, blocked.text

        gone = await client.delete(
            f"{BASE}/jobs/{job_id}/channels/{channel_id}/patch-points/{point_id}",
            headers=auth_headers,
        )
        assert gone.status_code == 204, gone.text
        dele = await client.delete(f"{BASE}/jobs/{job_id}/devices/{dev_id}", headers=auth_headers)
        assert dele.status_code == 204

        final = await client.get(f"{BASE}/jobs/{job_id}/devices", headers=auth_headers)
        assert final.json() == []


async def test_device_requires_job(auth_headers):
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        missing = await client.get(
            f"{BASE}/jobs/00000000-0000-0000-0000-000000000000/devices", headers=auth_headers
        )
        assert missing.status_code == 404


async def test_device_ports_roundtrip(auth_headers):
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        job = await client.post(
            f"{BASE}/jobs", json={"title": "DevJob2", "venue_name": "V"}, headers=auth_headers
        )
        assert job.status_code == 201, job.text
        job_id = job.json()["id"]

        ports = [
            {"direction": "in", "connector": "xlr", "count": 4},
            {"direction": "in", "connector": "trs", "count": 4},
            {"direction": "out", "connector": "xlr", "count": 8},
        ]
        dev = await client.post(
            f"{BASE}/jobs/{job_id}/devices",
            json={"name": "SB", "device_type": "digital_stagebox", "ports": ports},
            headers=auth_headers,
        )
        assert dev.status_code == 201, dev.text
        assert dev.json()["ports"] == ports

        # Update the ports list.
        new_ports = [{"direction": "out", "connector": "xlr", "count": 16}]
        upd = await client.patch(
            f"{BASE}/jobs/{job_id}/devices/{dev.json()['id']}",
            json={"ports": new_ports},
            headers=auth_headers,
        )
        assert upd.status_code == 200, upd.text
        assert upd.json()["ports"] == new_ports
