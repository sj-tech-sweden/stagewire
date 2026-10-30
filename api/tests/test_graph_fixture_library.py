import pytest
from httpx import ASGITransport, AsyncClient

from app.main import app

BASE = "/api/v1"


@pytest.mark.asyncio
async def test_fixtures_edited_through_the_graph_follow_the_type_library(auth_headers):
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        h = auth_headers
        job_id = (await client.post(f"{BASE}/jobs", json={"title": "Library"}, headers=h)).json()[
            "id"
        ]
        g = f"{BASE}/jobs/{job_id}/graph"
        fixture_type = (
            await client.post(
                f"{BASE}/jobs/{job_id}/fixture-types", json={"name": "LED wash"}, headers=h
            )
        ).json()
        for name, footprint in (("16ch", 16), ("8ch", 8)):
            res = await client.post(
                f"{BASE}/jobs/{job_id}/fixture-types/{fixture_type['id']}/modes",
                json={"name": name, "footprint": footprint},
                headers=h,
            )
            assert res.status_code == 201, res.text

        node = (
            await client.post(
                f"{g}/fixtures",
                json={"fixture_type": "led wash", "channel_mode": "16ch", "purpose": "FOH"},
                headers=h,
            )
        ).json()
        assert node["attributes"]["fixture_type"] == "LED wash"
        assert node["attributes"]["footprint"] == 16

        res = await client.patch(
            f"{g}/devices/{node['id']}",
            json={
                "attributes": {**node["attributes"], "channel_mode": "8ch"},
                "expected_revision": node["revision"],
            },
            headers=h,
        )
        assert res.status_code == 200, res.text
        legacy = (await client.get(f"{BASE}/jobs/{job_id}/fixtures", headers=h)).json()[0]
        assert (legacy["channel_mode"], legacy["footprint"]) == ("8ch", 8)
        refreshed = (await client.get(g, headers=h)).json()["devices"][0]
        assert refreshed["attributes"]["footprint"] == 8

        # a type typed in for the first time joins the library
        other = (
            await client.post(f"{g}/fixtures", json={"fixture_type": "Moving head"}, headers=h)
        ).json()
        assert other["attributes"]["fixture_type"] == "Moving head"
        names = {
            t["name"]
            for t in (await client.get(f"{BASE}/jobs/{job_id}/fixture-types", headers=h)).json()
        }
        assert names == {"LED wash", "Moving head"}
