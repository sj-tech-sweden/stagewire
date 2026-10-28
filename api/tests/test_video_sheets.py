from httpx import ASGITransport, AsyncClient

from app.main import app

BASE = "/api/v1"


async def test_each_device_gets_a_video_sheet_of_the_inputs_and_outputs_through_it(auth_headers):
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        job_id = (
            await client.post(f"{BASE}/jobs", json={"title": "Sheets"}, headers=auth_headers)
        ).json()["id"]
        cam_dev = (
            await client.post(
                f"{BASE}/jobs/{job_id}/devices",
                json={"name": "PTZ 1", "device_type": "ptz_camera"},
                headers=auth_headers,
            )
        ).json()
        switcher = (
            await client.post(
                f"{BASE}/jobs/{job_id}/devices",
                json={"name": "ATEM", "device_type": "switcher"},
                headers=auth_headers,
            )
        ).json()
        lst = (
            await client.post(
                f"{BASE}/jobs/{job_id}/video-lists", json={"name": "Cameras"}, headers=auth_headers
            )
        ).json()
        cam = (
            await client.post(
                f"{BASE}/jobs/{job_id}/video-lists/{lst['id']}/inputs",
                json={"source_label": "Cam 1 FOH", "connector": "sdi"},
                headers=auth_headers,
            )
        ).json()
        await client.put(
            f"{BASE}/jobs/{job_id}/video-inputs/{cam['id']}/patch-chain",
            json={
                "steps": [
                    {"device_id": cam_dev["id"], "connector": "sdi"},
                    {"device_id": switcher["id"], "connector": "hdmi", "patch_label": "2"},
                ]
            },
            headers=auth_headers,
        )
        out = (
            await client.post(
                f"{BASE}/jobs/{job_id}/video-lists/{lst['id']}/outputs",
                json={"name": "Program", "destination_label": "Front LED"},
                headers=auth_headers,
            )
        ).json()
        await client.put(
            f"{BASE}/jobs/{job_id}/video-outputs/{out['id']}/patch-chain",
            json={"steps": [{"device_id": switcher["id"], "connector": "hdmi"}]},
            headers=auth_headers,
        )

        sheets = (
            await client.get(f"{BASE}/jobs/{job_id}/video-patch-sheets", headers=auth_headers)
        ).json()
        by_name = {s["name"]: s for s in sheets}
        assert [r["kind"] for r in by_name["ATEM"]["rows"]] == ["input", "output"]
        cam_row = by_name["ATEM"]["rows"][0]
        assert cam_row["label"] == "Cam 1 FOH"
        assert cam_row["step"] == 2 and cam_row["steps"] == 2
        assert cam_row["patch_label"] == "2"
        out_row = by_name["ATEM"]["rows"][1]
        assert out_row["label"] == "Program" and out_row["detail"] == "Front LED"
        assert [r["label"] for r in by_name["PTZ 1"]["rows"]] == ["Cam 1 FOH"]
        assert by_name["PTZ 1"]["rows"][0]["step"] == 1
