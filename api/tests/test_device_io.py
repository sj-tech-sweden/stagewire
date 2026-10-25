from httpx import ASGITransport, AsyncClient

from app.main import app

BASE = "/api/v1"


async def test_mixer_io_defaults_come_from_the_patch_list_and_can_be_overridden(auth_headers):
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        job = (
            await client.post(f"{BASE}/jobs", json={"title": "IO job"}, headers=auth_headers)
        ).json()
        job_id = job["id"]

        lists = []
        for name, channel_count in (("FOH", 3), ("Monitors", 2)):
            cl = (
                await client.post(
                    f"{BASE}/jobs/{job_id}/channel-lists", json={"name": name}, headers=auth_headers
                )
            ).json()
            lists.append(cl["id"])
            for n in range(channel_count):
                await client.post(
                    f"{BASE}/jobs/{job_id}/channel-lists/{cl['id']}/channels",
                    json={"channel_number": n + 1, "source_label": f"{name} {n + 1}"},
                    headers=auth_headers,
                )
        for name in ("Main L", "Main R"):
            await client.post(
                f"{BASE}/jobs/{job_id}/channel-lists/{lists[0]}/outputs",
                json={"name": name},
                headers=auth_headers,
            )

        mixer = (
            await client.post(
                f"{BASE}/jobs/{job_id}/devices",
                json={"name": "FOH desk", "device_type": "mixer"},
                headers=auth_headers,
            )
        ).json()
        assert mixer["input_default"] == 5
        assert mixer["output_default"] == 2
        assert mixer["input_count"] == 5
        assert mixer["output_count"] == 2
        assert mixer["input_override"] is None

        overridden = await client.patch(
            f"{BASE}/jobs/{job_id}/devices/{mixer['id']}",
            json={"input_override": 48, "output_override": 16},
            headers=auth_headers,
        )
        assert overridden.status_code == 200, overridden.text
        assert overridden.json()["input_count"] == 48
        assert overridden.json()["output_count"] == 16
        assert overridden.json()["input_default"] == 5

        cleared = await client.patch(
            f"{BASE}/jobs/{job_id}/devices/{mixer['id']}",
            json={"input_override": None},
            headers=auth_headers,
        )
        assert cleared.json()["input_override"] is None
        assert cleared.json()["input_count"] == 5
        assert cleared.json()["output_override"] == 16

        stagebox = (
            await client.post(
                f"{BASE}/jobs/{job_id}/devices",
                json={"name": "Stagebox", "device_type": "digital_stagebox"},
                headers=auth_headers,
            )
        ).json()
        assert stagebox["input_default"] is None
        assert stagebox["input_count"] is None

        listed = (await client.get(f"{BASE}/jobs/{job_id}/devices", headers=auth_headers)).json()
        listed_mixer = next(d for d in listed if d["id"] == mixer["id"])
        assert listed_mixer["input_default"] == 5
        assert listed_mixer["output_count"] == 16
