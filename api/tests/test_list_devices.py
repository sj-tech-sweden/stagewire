from httpx import ASGITransport, AsyncClient

from app.main import app

BASE = "/api/v1"


async def test_each_sound_list_has_its_own_mixer_counts(auth_headers):
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        job_id = (
            await client.post(f"{BASE}/jobs", json={"title": "Two lists"}, headers=auth_headers)
        ).json()["id"]
        lists = {}
        for name, count in (("FOH", 3), ("Monitors", 1)):
            cl = (
                await client.post(
                    f"{BASE}/jobs/{job_id}/channel-lists", json={"name": name}, headers=auth_headers
                )
            ).json()
            lists[name] = cl["id"]
            for n in range(count):
                await client.post(
                    f"{BASE}/jobs/{job_id}/channel-lists/{cl['id']}/channels",
                    json={"channel_number": n + 1, "source_label": f"{name} {n + 1}"},
                    headers=auth_headers,
                )
        foh_mixer = (
            await client.post(
                f"{BASE}/jobs/{job_id}/devices",
                json={"name": "FOH · Mixer", "device_type": "mixer", "sound_list_id": lists["FOH"]},
                headers=auth_headers,
            )
        ).json()
        mon_mixer = (
            await client.post(
                f"{BASE}/jobs/{job_id}/devices",
                json={
                    "name": "Monitors · Mixer",
                    "device_type": "mixer",
                    "sound_list_id": lists["Monitors"],
                },
                headers=auth_headers,
            )
        ).json()
        assert foh_mixer["sound_list_id"] == lists["FOH"]
        assert foh_mixer["input_default"] == 3
        assert mon_mixer["input_default"] == 1


async def test_a_list_rejects_a_list_from_another_job(auth_headers):
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        job_a = (
            await client.post(f"{BASE}/jobs", json={"title": "A"}, headers=auth_headers)
        ).json()["id"]
        job_b = (
            await client.post(f"{BASE}/jobs", json={"title": "B"}, headers=auth_headers)
        ).json()["id"]
        foreign = (
            await client.post(
                f"{BASE}/jobs/{job_b}/channel-lists", json={"name": "Other"}, headers=auth_headers
            )
        ).json()["id"]
        res = await client.post(
            f"{BASE}/jobs/{job_a}/devices",
            json={"name": "Mixer", "device_type": "mixer", "sound_list_id": foreign},
            headers=auth_headers,
        )
        assert res.status_code == 422


async def test_each_video_list_gets_its_own_switcher_named_after_it(auth_headers):
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        job_id = (
            await client.post(f"{BASE}/jobs", json={"title": "Video lists"}, headers=auth_headers)
        ).json()["id"]
        made = {}
        for name, product in (("Cameras", "11"), ("Graphics", "22")):
            lst = (
                await client.post(
                    f"{BASE}/jobs/{job_id}/video-lists", json={"name": name}, headers=auth_headers
                )
            ).json()
            await client.patch(
                f"{BASE}/jobs/{job_id}/video-lists/{lst['id']}",
                json={"switcher_product_id": product, "switcher_product_name": f"ATEM {product}"},
                headers=auth_headers,
            )
            cam = (
                await client.post(
                    f"{BASE}/jobs/{job_id}/video-lists/{lst['id']}/inputs",
                    json={"source_label": f"{name} 1"},
                    headers=auth_headers,
                )
            ).json()
            fill = (
                await client.post(
                    f"{BASE}/jobs/{job_id}/video-lists/{lst['id']}/fill-from-switcher",
                    headers=auth_headers,
                )
            ).json()
            made[name] = fill["device_id"]
            assert cam["id"]
        assert made["Cameras"] != made["Graphics"]
        devices = (await client.get(f"{BASE}/jobs/{job_id}/devices", headers=auth_headers)).json()
        by_id = {d["id"]: d for d in devices}
        assert by_id[made["Cameras"]]["name"].startswith("Cameras")
        assert by_id[made["Graphics"]]["name"].startswith("Graphics")
        assert by_id[made["Cameras"]]["video_list_id"] is not None
