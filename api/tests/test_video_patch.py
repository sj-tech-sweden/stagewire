from uuid import uuid4

from httpx import ASGITransport, AsyncClient

from app.main import app

BASE = "/api/v1"


async def _job(client, headers, title="Video job"):
    res = await client.post(f"{BASE}/jobs", json={"title": title}, headers=headers)
    assert res.status_code == 201, res.text
    return res.json()["id"]


async def _device(client, headers, job_id, name, device_type):
    res = await client.post(
        f"{BASE}/jobs/{job_id}/devices",
        json={"name": name, "device_type": device_type},
        headers=headers,
    )
    assert res.status_code == 201, res.text
    return res.json()["id"]


async def test_camera_inputs_patch_through_a_switcher(auth_headers):
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        job_id = await _job(client, auth_headers)
        switcher = await _device(client, auth_headers, job_id, "ATEM", "switcher")

        lst = (
            await client.post(
                f"{BASE}/jobs/{job_id}/video-lists", json={"name": "Cameras"}, headers=auth_headers
            )
        ).json()
        assert lst["name"] == "Cameras" and lst["inputs"] == []

        first = await client.post(
            f"{BASE}/jobs/{job_id}/video-lists/{lst['id']}/inputs",
            json={"source_label": "Cam 1 FOH", "source_type": "camera", "connector": "sdi"},
            headers=auth_headers,
        )
        assert first.status_code == 201, first.text
        assert first.json()["input_number"] == 1
        second = await client.post(
            f"{BASE}/jobs/{job_id}/video-lists/{lst['id']}/inputs",
            json={"source_label": "Cam 2 Stage", "connector": "hdmi"},
            headers=auth_headers,
        )
        assert second.json()["input_number"] == 2
        assert second.json()["connector"] == "hdmi"
        input_id = first.json()["id"]

        point = await client.post(
            f"{BASE}/jobs/{job_id}/video-inputs/{input_id}/patch-points",
            json={"position": 0, "connector": "sdi", "device_id": switcher},
            headers=auth_headers,
        )
        assert point.status_code == 201, point.text
        point_id = point.json()["id"]

        no_device = await client.post(
            f"{BASE}/jobs/{job_id}/video-inputs/{input_id}/patch-points",
            json={"position": 1},
            headers=auth_headers,
        )
        assert no_device.status_code == 422

        other_job = await _job(client, auth_headers, title="Other")
        foreign = await _device(client, auth_headers, other_job, "Other router", "router")
        wrong = await client.post(
            f"{BASE}/jobs/{job_id}/video-inputs/{input_id}/patch-points",
            json={"position": 1, "device_id": foreign},
            headers=auth_headers,
        )
        assert wrong.status_code == 422

        listed = (
            await client.get(f"{BASE}/jobs/{job_id}/video-lists", headers=auth_headers)
        ).json()
        inputs = listed[0]["inputs"]
        assert [i["input_number"] for i in inputs] == [1, 2]
        assert inputs[0]["patch_points"][0]["id"] == point_id
        assert inputs[0]["patch_points"][0]["device_id"] == switcher

        renamed = await client.patch(
            f"{BASE}/jobs/{job_id}/video-inputs/{input_id}",
            json={"source_label": "Cam 1 Wide"},
            headers=auth_headers,
        )
        assert renamed.json()["source_label"] == "Cam 1 Wide"


async def test_camera_element_links_to_a_video_input_and_can_unlink(auth_headers):
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        job_id = await _job(client, auth_headers)
        lst = (
            await client.post(
                f"{BASE}/jobs/{job_id}/video-lists", json={"name": "Cameras"}, headers=auth_headers
            )
        ).json()
        cam = (
            await client.post(
                f"{BASE}/jobs/{job_id}/video-lists/{lst['id']}/inputs",
                json={"source_label": "Cam 1"},
                headers=auth_headers,
            )
        ).json()
        element = await client.post(
            f"{BASE}/jobs/{job_id}/plot-elements",
            json={
                "element_type": "camera",
                "label": "Cam 1",
                "position_x": 100,
                "position_y": 50,
                "linked_video_input_id": cam["id"],
            },
            headers=auth_headers,
        )
        assert element.status_code == 201, element.text
        assert element.json()["linked_video_input_id"] == cam["id"]

        unlinked = await client.patch(
            f"{BASE}/jobs/{job_id}/plot-elements/{element.json()['id']}",
            json={"linked_video_input_id": None},
            headers=auth_headers,
        )
        assert unlinked.json()["linked_video_input_id"] is None


async def test_deleting_an_input_removes_its_patch_points_and_unknown_ids_404(auth_headers):
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        job_id = await _job(client, auth_headers)
        switcher = await _device(client, auth_headers, job_id, "ATEM", "switcher")
        lst = (
            await client.post(
                f"{BASE}/jobs/{job_id}/video-lists", json={"name": "Cameras"}, headers=auth_headers
            )
        ).json()
        cam = (
            await client.post(
                f"{BASE}/jobs/{job_id}/video-lists/{lst['id']}/inputs",
                json={"source_label": "Cam 1"},
                headers=auth_headers,
            )
        ).json()
        await client.post(
            f"{BASE}/jobs/{job_id}/video-inputs/{cam['id']}/patch-points",
            json={"device_id": switcher},
            headers=auth_headers,
        )

        deleted = await client.delete(
            f"{BASE}/jobs/{job_id}/video-inputs/{cam['id']}", headers=auth_headers
        )
        assert deleted.status_code == 204
        listed = (
            await client.get(f"{BASE}/jobs/{job_id}/video-lists", headers=auth_headers)
        ).json()
        assert listed[0]["inputs"] == []

        missing = await client.get(f"{BASE}/jobs/{uuid4()}/video-lists", headers=auth_headers)
        assert missing.status_code == 404
        gone = await client.patch(
            f"{BASE}/jobs/{job_id}/video-inputs/{uuid4()}",
            json={"source_label": "x"},
            headers=auth_headers,
        )
        assert gone.status_code == 404


async def test_device_with_video_patch_points_cannot_be_deleted(auth_headers):
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        job_id = await _job(client, auth_headers)
        switcher = await _device(client, auth_headers, job_id, "ATEM", "switcher")
        lst = (
            await client.post(
                f"{BASE}/jobs/{job_id}/video-lists", json={"name": "Cameras"}, headers=auth_headers
            )
        ).json()
        cam = (
            await client.post(
                f"{BASE}/jobs/{job_id}/video-lists/{lst['id']}/inputs",
                json={"source_label": "Cam 1"},
                headers=auth_headers,
            )
        ).json()
        point = await client.post(
            f"{BASE}/jobs/{job_id}/video-inputs/{cam['id']}/patch-points",
            json={"device_id": switcher},
            headers=auth_headers,
        )
        assert point.status_code == 201

        blocked = await client.delete(
            f"{BASE}/jobs/{job_id}/devices/{switcher}", headers=auth_headers
        )
        assert blocked.status_code == 409

        await client.delete(
            f"{BASE}/jobs/{job_id}/video-inputs/{cam['id']}/patch-points/{point.json()['id']}",
            headers=auth_headers,
        )
        freed = await client.delete(
            f"{BASE}/jobs/{job_id}/devices/{switcher}", headers=auth_headers
        )
        assert freed.status_code == 204
