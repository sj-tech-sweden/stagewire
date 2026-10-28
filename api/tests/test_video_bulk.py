from httpx import ASGITransport, AsyncClient

from app.main import app

BASE = "/api/v1"


async def _setup(client, headers):
    job_id = (
        await client.post(f"{BASE}/jobs", json={"title": "Bulk video"}, headers=headers)
    ).json()["id"]
    switcher = (
        await client.post(
            f"{BASE}/jobs/{job_id}/devices",
            json={"name": "ATEM", "device_type": "switcher"},
            headers=headers,
        )
    ).json()
    lst = (
        await client.post(
            f"{BASE}/jobs/{job_id}/video-lists", json={"name": "Cameras"}, headers=headers
        )
    ).json()
    return job_id, switcher["id"], lst["id"]


async def test_bulk_inputs_number_from_start_and_patch_to_the_device(auth_headers):
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        job_id, switcher, list_id = await _setup(client, auth_headers)
        res = await client.post(
            f"{BASE}/jobs/{job_id}/video-lists/{list_id}/inputs/bulk",
            json={"quantity": 4, "start_number": 5, "prefix": "Cam", "device_id": switcher},
            headers=auth_headers,
        )
        assert res.status_code == 201, res.text
        created = res.json()
        assert [i["input_number"] for i in created] == [5, 6, 7, 8]
        assert created[0]["source_label"] == "Cam 5"
        assert created[3]["patch_points"][0]["device_id"] == switcher

        listed = (
            await client.get(f"{BASE}/jobs/{job_id}/video-lists", headers=auth_headers)
        ).json()
        assert len(listed[0]["inputs"]) == 4

        bad = await client.post(
            f"{BASE}/jobs/{job_id}/video-lists/{list_id}/inputs/bulk",
            json={"quantity": 0},
            headers=auth_headers,
        )
        assert bad.status_code == 422
        too_many = await client.post(
            f"{BASE}/jobs/{job_id}/video-lists/{list_id}/inputs/bulk",
            json={"quantity": 500},
            headers=auth_headers,
        )
        assert too_many.status_code == 422


async def test_bulk_outputs_and_output_patch_points(auth_headers):
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        job_id, switcher, list_id = await _setup(client, auth_headers)
        res = await client.post(
            f"{BASE}/jobs/{job_id}/video-lists/{list_id}/outputs/bulk",
            json={"quantity": 3, "prefix": "LED", "connector": "hdmi"},
            headers=auth_headers,
        )
        assert res.status_code == 201, res.text
        outputs = res.json()
        assert [o["name"] for o in outputs] == ["LED 1", "LED 2", "LED 3"]
        assert outputs[0]["connector"] == "hdmi"
        out_id = outputs[0]["id"]

        foreign_job = (
            await client.post(f"{BASE}/jobs", json={"title": "Other"}, headers=auth_headers)
        ).json()["id"]
        foreign = (
            await client.post(
                f"{BASE}/jobs/{foreign_job}/devices",
                json={"name": "Other", "device_type": "router"},
                headers=auth_headers,
            )
        ).json()["id"]
        wrong = await client.post(
            f"{BASE}/jobs/{job_id}/video-outputs/{out_id}/patch-points",
            json={"device_id": foreign},
            headers=auth_headers,
        )
        assert wrong.status_code == 422

        point = await client.post(
            f"{BASE}/jobs/{job_id}/video-outputs/{out_id}/patch-points",
            json={"device_id": switcher},
            headers=auth_headers,
        )
        assert point.status_code == 201, point.text
        renamed = await client.patch(
            f"{BASE}/jobs/{job_id}/video-outputs/{out_id}",
            json={"destination_label": "Front LED wall"},
            headers=auth_headers,
        )
        assert renamed.json()["destination_label"] == "Front LED wall"

        devices = (await client.get(f"{BASE}/jobs/{job_id}/devices", headers=auth_headers)).json()
        assert next(d for d in devices if d["id"] == switcher)["output_default"] == 1

        deleted = await client.delete(
            f"{BASE}/jobs/{job_id}/video-outputs/{out_id}", headers=auth_headers
        )
        assert deleted.status_code == 204


async def test_switcher_product_on_the_list_can_be_set_and_cleared(auth_headers):
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        job_id, _, list_id = await _setup(client, auth_headers)
        set_res = await client.patch(
            f"{BASE}/jobs/{job_id}/video-lists/{list_id}",
            json={
                "switcher_product_id": "123",
                "switcher_product_name": "ATEM Mini Pro",
                "switcher_inputs": 4,
                "switcher_outputs": 2,
            },
            headers=auth_headers,
        )
        assert set_res.status_code == 200, set_res.text
        assert set_res.json()["switcher_product_name"] == "ATEM Mini Pro"
        assert set_res.json()["switcher_inputs"] == 4

        cleared = await client.patch(
            f"{BASE}/jobs/{job_id}/video-lists/{list_id}",
            json={"switcher_product_id": None, "switcher_product_name": None},
            headers=auth_headers,
        )
        assert cleared.json()["switcher_product_id"] is None
        assert cleared.json()["switcher_inputs"] == 4
        assert cleared.json()["name"] == "Cameras"
