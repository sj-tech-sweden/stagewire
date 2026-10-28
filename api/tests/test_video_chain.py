from httpx import ASGITransport, AsyncClient

from app.main import app

BASE = "/api/v1"


async def _device(client, headers, job_id, name, device_type):
    return (
        await client.post(
            f"{BASE}/jobs/{job_id}/devices",
            json={"name": name, "device_type": device_type},
            headers=headers,
        )
    ).json()


async def test_a_whole_input_chain_is_replaced_in_order(auth_headers):
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        job_id = (
            await client.post(f"{BASE}/jobs", json={"title": "Chain"}, headers=auth_headers)
        ).json()["id"]
        camera = await _device(client, auth_headers, job_id, "PTZ 1", "ptz_camera")
        patchbay = await _device(client, auth_headers, job_id, "Patchbay A", "patchbay")
        switcher = await _device(client, auth_headers, job_id, "ATEM", "switcher")
        projector = await _device(client, auth_headers, job_id, "Projector FOH", "projector")
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

        chain = await client.put(
            f"{BASE}/jobs/{job_id}/video-inputs/{inp['id']}/patch-chain",
            json={
                "steps": [
                    {"device_id": camera["id"], "connector": "sdi", "patch_label": "Cam 1"},
                    {"device_id": patchbay["id"], "connector": "sdi", "patch_label": "A1"},
                    {"device_id": switcher["id"], "connector": "sdi", "patch_label": "3"},
                ]
            },
            headers=auth_headers,
        )
        assert chain.status_code == 200, chain.text
        assert [p["device_id"] for p in chain.json()["patch_points"]] == [
            camera["id"],
            patchbay["id"],
            switcher["id"],
        ]

        reordered = await client.put(
            f"{BASE}/jobs/{job_id}/video-inputs/{inp['id']}/patch-chain",
            json={"steps": [{"device_id": switcher["id"]}, {"device_id": projector["id"]}]},
            headers=auth_headers,
        )
        assert [p["device_id"] for p in reordered.json()["patch_points"]] == [
            switcher["id"],
            projector["id"],
        ]
        listed = (
            await client.get(f"{BASE}/jobs/{job_id}/video-lists", headers=auth_headers)
        ).json()
        assert len(listed[0]["inputs"][0]["patch_points"]) == 2

        other_job = (
            await client.post(f"{BASE}/jobs", json={"title": "Other"}, headers=auth_headers)
        ).json()["id"]
        foreign = await _device(client, auth_headers, other_job, "Foreign", "router")
        wrong = await client.put(
            f"{BASE}/jobs/{job_id}/video-inputs/{inp['id']}/patch-chain",
            json={"steps": [{"device_id": foreign["id"]}]},
            headers=auth_headers,
        )
        assert wrong.status_code == 422

        cleared = await client.put(
            f"{BASE}/jobs/{job_id}/video-inputs/{inp['id']}/patch-chain",
            json={"steps": []},
            headers=auth_headers,
        )
        assert cleared.json()["patch_points"] == []


async def test_a_whole_output_chain_is_replaced_in_order(auth_headers):
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        job_id = (
            await client.post(f"{BASE}/jobs", json={"title": "Out chain"}, headers=auth_headers)
        ).json()["id"]
        switcher = await _device(client, auth_headers, job_id, "ATEM", "switcher")
        converter = await _device(client, auth_headers, job_id, "Converter", "converter")
        screen = await _device(client, auth_headers, job_id, "LED wall", "screen")
        lst = (
            await client.post(
                f"{BASE}/jobs/{job_id}/video-lists", json={"name": "Outputs"}, headers=auth_headers
            )
        ).json()
        out = (
            await client.post(
                f"{BASE}/jobs/{job_id}/video-lists/{lst['id']}/outputs",
                json={"name": "Program"},
                headers=auth_headers,
            )
        ).json()
        chain = await client.put(
            f"{BASE}/jobs/{job_id}/video-outputs/{out['id']}/patch-chain",
            json={
                "steps": [
                    {"device_id": switcher["id"], "connector": "hdmi"},
                    {"device_id": converter["id"], "connector": "sdi"},
                    {"device_id": screen["id"], "connector": "hdmi", "patch_label": "Front"},
                ]
            },
            headers=auth_headers,
        )
        assert chain.status_code == 200, chain.text
        assert [p["device_id"] for p in chain.json()["patch_points"]] == [
            switcher["id"],
            converter["id"],
            screen["id"],
        ]
        assert chain.json()["patch_points"][2]["patch_label"] == "Front"


async def test_a_chain_step_keeps_the_output_port_it_takes_and_the_input_port_it_feeds(
    auth_headers,
):
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        job_id = (
            await client.post(f"{BASE}/jobs", json={"title": "Ports"}, headers=auth_headers)
        ).json()["id"]
        switcher = await _device(client, auth_headers, job_id, "ATEM", "switcher")
        projector = await _device(client, auth_headers, job_id, "Projector FOH", "projector")
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
        chained = await client.put(
            f"{BASE}/jobs/{job_id}/video-inputs/{inp['id']}/patch-chain",
            json={
                "steps": [
                    {"device_id": switcher["id"], "input_port": "IN 1", "source_port": ""},
                    {"device_id": projector["id"], "source_port": "OUT 3", "input_port": "HDMI 1"},
                ]
            },
            headers=auth_headers,
        )
        assert chained.status_code == 200, chained.text
        points = chained.json()["patch_points"]
        assert (points[1]["source_port"], points[1]["input_port"]) == ("OUT 3", "HDMI 1")
        assert (points[0]["source_port"], points[0]["input_port"]) == ("", "IN 1")
