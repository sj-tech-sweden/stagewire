"""Read-only share tokens for the day-of-show crew mobile view.

A logged-in user mints a token (``POST /jobs/{job_id}/share``); the token grants
view-only access to ``GET /jobs/{job_id}/mobile-view`` with no session. No write
path is exposed, and the token is scoped to a single job.
"""

from httpx import ASGITransport, AsyncClient

from app.main import app

BASE = "/api/v1"


async def _make_job(client, headers):
    resp = await client.post(f"{BASE}/jobs", json={"title": "Share test job"}, headers=headers)
    assert resp.status_code < 300, resp.text
    return resp.json()["id"]


async def test_share_flow_roundtrip(auth_headers):
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        job_id = await _make_job(client, auth_headers)
        await client.post(
            f"{BASE}/jobs/{job_id}/graph/devices",
            json={"domain": "audio", "name": "Lead mic", "kind": "microphone"},
            headers=auth_headers,
        )

        # Minting requires a session.
        anon = await client.post(f"{BASE}/jobs/{job_id}/share")
        assert anon.status_code == 401

        minted = await client.post(f"{BASE}/jobs/{job_id}/share", headers=auth_headers)
        assert minted.status_code == 200
        token = minted.json()["token"]

        # The mobile view is reachable with only the token, no login.
        view = await client.get(
            f"{BASE}/jobs/{job_id}/mobile-view", params={"token": token}
        )
        assert view.status_code == 200, view.text
        body = view.json()
        assert body["job"]["id"] == job_id
        assert any(d["name"] == "Lead mic" for d in body["graph"]["devices"])

        # A forged/tampered token is rejected.
        bad = await client.get(
            f"{BASE}/jobs/{job_id}/mobile-view", params={"token": token + "x"}
        )
        assert bad.status_code == 401


async def test_share_token_is_job_scoped(auth_headers):
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        job_a = await _make_job(client, auth_headers)
        job_b = await _make_job(client, auth_headers)
        token = (
            await client.post(f"{BASE}/jobs/{job_a}/share", headers=auth_headers)
        ).json()["token"]

        # Token for job A must not open job B.
        other = await client.get(
            f"{BASE}/jobs/{job_b}/mobile-view", params={"token": token}
        )
        assert other.status_code == 401
