from httpx import ASGITransport, AsyncClient

from app.main import app

BASE = "/api/v1"


async def test_setting_a_switcher_creates_its_device_and_the_remaining_inputs_and_outputs(
    auth_headers,
):
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        job_id = (
            await client.post(f"{BASE}/jobs", json={"title": "Fill video"}, headers=auth_headers)
        ).json()["id"]
        lst = (
            await client.post(
                f"{BASE}/jobs/{job_id}/video-lists", json={"name": "Cameras"}, headers=auth_headers
            )
        ).json()
        other = (
            await client.post(
                f"{BASE}/jobs/{job_id}/devices",
                json={"name": "Router", "device_type": "router"},
                headers=auth_headers,
            )
        ).json()
        kept = (
            await client.post(
                f"{BASE}/jobs/{job_id}/video-lists/{lst['id']}/inputs",
                json={"source_label": "Cam 1"},
                headers=auth_headers,
            )
        ).json()
        await client.post(
            f"{BASE}/jobs/{job_id}/video-inputs/{kept['id']}/patch-points",
            json={"device_id": other["id"]},
            headers=auth_headers,
        )
        free = (
            await client.post(
                f"{BASE}/jobs/{job_id}/video-lists/{lst['id']}/inputs",
                json={"source_label": "Cam 2"},
                headers=auth_headers,
            )
        ).json()
        await client.post(
            f"{BASE}/jobs/{job_id}/video-lists/{lst['id']}/outputs/bulk",
            json={"quantity": 1, "prefix": "Program"},
            headers=auth_headers,
        )

        set_switcher = await client.patch(
            f"{BASE}/jobs/{job_id}/video-lists/{lst['id']}",
            json={
                "switcher_product_id": "777",
                "switcher_product_name": "ATEM 8",
                "switcher_inputs": 4,
                "switcher_outputs": 2,
            },
            headers=auth_headers,
        )
        assert set_switcher.status_code == 200, set_switcher.text

        fill = await client.post(
            f"{BASE}/jobs/{job_id}/video-lists/{lst['id']}/fill-from-switcher", headers=auth_headers
        )
        assert fill.status_code == 200, fill.text
        result = fill.json()
        assert result["inputs_added"] == 2
        assert result["inputs_patched"] == 1
        assert result["outputs_added"] == 1
        assert result["outputs_patched"] == 1

        devices = (await client.get(f"{BASE}/jobs/{job_id}/devices", headers=auth_headers)).json()
        switcher = next(d for d in devices if d["device_type"] == "switcher")
        assert switcher["stockwire_product_id"] == "777"
        assert switcher["id"] == result["device_id"]

        listed = (
            await client.get(f"{BASE}/jobs/{job_id}/video-lists", headers=auth_headers)
        ).json()[0]
        assert len(listed["inputs"]) == 4
        assert [i["input_number"] for i in listed["inputs"]] == [1, 2, 3, 4]
        by_id = {i["id"]: i for i in listed["inputs"]}
        assert by_id[kept["id"]]["patch_points"][0]["device_id"] == other["id"]
        assert by_id[free["id"]]["patch_points"][0]["device_id"] == switcher["id"]
        assert [o["patch_points"][0]["device_id"] for o in listed["outputs"]] == [
            switcher["id"],
            switcher["id"],
        ]

        again = (
            await client.post(
                f"{BASE}/jobs/{job_id}/video-lists/{lst['id']}/fill-from-switcher",
                headers=auth_headers,
            )
        ).json()
        assert again["inputs_added"] == 0 and again["outputs_added"] == 0
        assert (
            len((await client.get(f"{BASE}/jobs/{job_id}/devices", headers=auth_headers)).json())
            == 2
        )


async def test_input_and_output_can_be_edited_after_creation(auth_headers):
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        job_id = (
            await client.post(f"{BASE}/jobs", json={"title": "Edit video"}, headers=auth_headers)
        ).json()["id"]
        lst = (
            await client.post(
                f"{BASE}/jobs/{job_id}/video-lists", json={"name": "Cameras"}, headers=auth_headers
            )
        ).json()
        inp = (
            await client.post(
                f"{BASE}/jobs/{job_id}/video-lists/{lst['id']}/inputs",
                json={"source_label": "Cam 1"},
                headers=auth_headers,
            )
        ).json()
        edited = await client.patch(
            f"{BASE}/jobs/{job_id}/video-inputs/{inp['id']}",
            json={"input_number": 7, "source_type": "ptz", "connector": "hdmi", "notes": "Balcony"},
            headers=auth_headers,
        )
        assert edited.status_code == 200, edited.text
        assert edited.json()["input_number"] == 7
        assert edited.json()["notes"] == "Balcony"
        out = (
            await client.post(
                f"{BASE}/jobs/{job_id}/video-lists/{lst['id']}/outputs",
                json={"name": "Program"},
                headers=auth_headers,
            )
        ).json()
        renamed = await client.patch(
            f"{BASE}/jobs/{job_id}/video-outputs/{out['id']}",
            json={"output_number": 3, "name": "Clean feed"},
            headers=auth_headers,
        )
        assert renamed.json()["output_number"] == 3
        assert renamed.json()["name"] == "Clean feed"
