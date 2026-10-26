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


async def test_switcher_io_comes_from_video_inputs_then_stockwire_then_override(
    auth_headers, monkeypatch
):
    from app.domains.audio import router as audio_router

    products = {
        "999": {
            "name": "ATEM 8",
            "specs": {"inputs": 8, "outputs": 4, "connectors": ["sdi", "hdmi"]},
        }
    }

    async def fake_fetcher(db):
        async def fetch(product_id):
            return products.get(str(product_id))

        return fetch

    monkeypatch.setattr(audio_router, "stockwire_product_fetcher", fake_fetcher)

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        job_id = (
            await client.post(f"{BASE}/jobs", json={"title": "Switcher job"}, headers=auth_headers)
        ).json()["id"]
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
        for n in range(2):
            cam = (
                await client.post(
                    f"{BASE}/jobs/{job_id}/video-lists/{lst['id']}/inputs",
                    json={"source_label": f"Cam {n + 1}"},
                    headers=auth_headers,
                )
            ).json()
            await client.post(
                f"{BASE}/jobs/{job_id}/video-inputs/{cam['id']}/patch-points",
                json={"device_id": switcher["id"]},
                headers=auth_headers,
            )

        patch_only = (
            await client.get(f"{BASE}/jobs/{job_id}/devices", headers=auth_headers)
        ).json()[0]
        assert patch_only["input_default"] == 2
        assert patch_only["input_count"] == 2
        assert patch_only["input_source"] == "patch"
        assert patch_only["output_count"] is None

        linked = await client.patch(
            f"{BASE}/jobs/{job_id}/devices/{switcher['id']}",
            json={"stockwire_product_id": "999", "stockwire_product_name": "ATEM 8"},
            headers=auth_headers,
        )
        assert linked.status_code == 200, linked.text
        from_stockwire = linked.json()
        assert from_stockwire["input_count"] == 8
        assert from_stockwire["input_source"] == "stockwire"
        assert from_stockwire["output_count"] == 4
        assert from_stockwire["output_source"] == "stockwire"
        assert from_stockwire["stockwire_connectors"] == ["sdi", "hdmi"]
        assert from_stockwire["input_default"] == 2

        overridden = await client.patch(
            f"{BASE}/jobs/{job_id}/devices/{switcher['id']}",
            json={"input_override": 10},
            headers=auth_headers,
        )
        assert overridden.json()["input_count"] == 10
        assert overridden.json()["input_source"] == "override"
