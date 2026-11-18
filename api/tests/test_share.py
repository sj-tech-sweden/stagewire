"""Job-scoped share tokens for the day-of-show crew mobile view.

A logged-in user mints a token (``POST /jobs/{job_id}/share``); the token grants
view-only access to ``GET /jobs/{job_id}/mobile-view`` by default. Asset binding is an
explicit token capability and remains scoped to a single job.
"""

from httpx import ASGITransport, AsyncClient

from app.domains.share import router as share_router
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
        view = await client.get(f"{BASE}/jobs/{job_id}/mobile-view", params={"token": token})
        assert view.status_code == 200, view.text
        body = view.json()
        assert body["job"]["id"] == job_id
        assert body["can_bind_assets"] is False
        assert any(d["name"] == "Lead mic" for d in body["graph"]["devices"])

        # A forged/tampered token is rejected.
        bad = await client.get(f"{BASE}/jobs/{job_id}/mobile-view", params={"token": token + "x"})
        assert bad.status_code == 401


async def test_share_token_is_job_scoped(auth_headers):
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        job_a = await _make_job(client, auth_headers)
        job_b = await _make_job(client, auth_headers)
        token = (await client.post(f"{BASE}/jobs/{job_a}/share", headers=auth_headers)).json()[
            "token"
        ]

        # Token for job A must not open job B.
        other = await client.get(f"{BASE}/jobs/{job_b}/mobile-view", params={"token": token})
        assert other.status_code == 401


async def test_asset_binding_requires_explicit_job_scoped_share_permission(
    auth_headers, monkeypatch
):
    class FakeStockwire:
        async def list_product_devices(self, product_id):
            return [
                {
                    "id": "asset-1",
                    "product_id": product_id,
                    "asset_tag": "TAG-1",
                    "internal_note": "not for crew",
                }
            ]

    async def fake_catalog_client(db):
        return FakeStockwire()

    monkeypatch.setattr(share_router, "_catalog_client", fake_catalog_client)
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        job_id = await _make_job(client, auth_headers)
        job_b = await _make_job(client, auth_headers)
        device = await client.post(
            f"{BASE}/jobs/{job_id}/graph/devices",
            json={
                "domain": "audio",
                "name": "Stagebox",
                "kind": "stagebox",
                "stockwire_product_id": "77",
            },
            headers=auth_headers,
        )
        device_id = device.json()["id"]

        view_token = (
            await client.post(f"{BASE}/jobs/{job_id}/share", headers=auth_headers)
        ).json()["token"]
        denied = await client.post(
            f"{BASE}/jobs/{job_id}/devices/{device_id}/bind-asset",
            params={"token": view_token},
            json={"code": "ASSET-1", "expected_revision": 1},
        )
        assert denied.status_code == 403
        hidden_assets = await client.get(
            f"{BASE}/jobs/{job_id}/devices/{device_id}/stockwire-assets",
            params={"token": view_token},
        )
        assert hidden_assets.status_code == 403

        binding_token = (
            await client.post(
                f"{BASE}/jobs/{job_id}/share",
                headers=auth_headers,
                params={"allow_asset_binding": True},
            )
        ).json()["token"]
        view = await client.get(
            f"{BASE}/jobs/{job_id}/mobile-view", params={"token": binding_token}
        )
        assert view.json()["can_bind_assets"] is True

        channel = await client.post(
            f"{BASE}/jobs/{job_id}/graph/devices",
            json={"domain": "audio", "name": "Channel 1", "kind": "channel"},
            headers=auth_headers,
        )
        channel_id = channel.json()["id"]
        virtual_bind = await client.post(
            f"{BASE}/jobs/{job_id}/devices/{channel_id}/bind-asset",
            params={"token": binding_token},
            json={"code": "ASSET-1", "expected_revision": 1},
        )
        assert virtual_bind.status_code == 422
        virtual_unbind = await client.delete(
            f"{BASE}/jobs/{job_id}/devices/{channel_id}/asset-binding",
            params={"token": binding_token, "expected_revision": 1},
        )
        assert virtual_unbind.status_code == 422

        assets = await client.get(
            f"{BASE}/jobs/{job_id}/devices/{device_id}/stockwire-assets",
            params={"token": binding_token},
        )
        assert assets.status_code == 200
        assert assets.json()["items"] == [
            {"id": "asset-1", "product_id": "77", "asset_tag": "TAG-1"}
        ]

        wrong_job = await client.post(
            f"{BASE}/jobs/{job_b}/devices/{device_id}/bind-asset",
            params={"token": binding_token},
            json={"code": "ASSET-1", "expected_revision": 1},
        )
        assert wrong_job.status_code == 401

        bound = await client.post(
            f"{BASE}/jobs/{job_id}/devices/{device_id}/bind-asset",
            params={"token": binding_token},
            json={
                "code": "ASSET-1",
                "asset_id": "asset-1",
                "expected_revision": 1,
            },
        )
        assert bound.status_code == 200, bound.text
        assert bound.json()["attributes"]["stockwire_asset_code"] == "ASSET-1"
        assert bound.json()["stockwire_device_id"] == "asset-1"

        unbound = await client.delete(
            f"{BASE}/jobs/{job_id}/devices/{device_id}/asset-binding",
            params={
                "token": binding_token,
                "expected_revision": bound.json()["revision"],
            },
        )
        assert unbound.status_code == 200, unbound.text
        assert unbound.json()["attributes"]["stockwire_asset_code"] is None
        assert unbound.json()["stockwire_device_id"] is None

        stale_unbind = await client.delete(
            f"{BASE}/jobs/{job_id}/devices/{device_id}/asset-binding",
            params={"token": binding_token, "expected_revision": bound.json()["revision"]},
        )
        assert stale_unbind.status_code == 409
        assert stale_unbind.json()["detail"]["code"] == "revision_conflict"


async def test_share_token_carries_creator_locale(auth_headers):
    """The creator's locale is embedded in the token and echoed by the mobile view, so the
    link itself carries the language a crew member should see."""
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        from app.domains.auth.security import decode_token

        job_id = await _make_job(client, auth_headers)

        minted = await client.post(
            f"{BASE}/jobs/{job_id}/share",
            headers=auth_headers,
            params={"locale": "sv"},
        )
        assert minted.status_code == 200
        token = minted.json()["token"]

        # The locale travels inside the JWT (so the link carries it, no DB record needed).
        assert decode_token(token)["locale"] == "sv"

        view = await client.get(f"{BASE}/jobs/{job_id}/mobile-view", params={"token": token})
        assert view.status_code == 200
        assert view.json()["locale"] == "sv"


async def test_share_token_drops_unsupported_locale(auth_headers):
    """An unsupported or missing locale is ignored so the view falls back to its own default."""
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        job_id = await _make_job(client, auth_headers)

        minted = await client.post(
            f"{BASE}/jobs/{job_id}/share",
            headers=auth_headers,
            params={"locale": "fr"},
        )
        assert minted.status_code == 200
        token = minted.json()["token"]

        view = await client.get(f"{BASE}/jobs/{job_id}/mobile-view", params={"token": token})
        assert view.status_code == 200
        assert view.json()["locale"] is None


async def test_crew_sheets_are_read_only_and_scoped_by_the_share_token(auth_headers):
    """The crew view's sound / lights / video lists: token-only and job-scoped."""
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        h = auth_headers
        job_id = await _make_job(client, h)
        other_job = await _make_job(client, h)
        lst = (
            await client.post(
                f"{BASE}/jobs/{job_id}/channel-lists", json={"name": "FOH"}, headers=h
            )
        ).json()
        await client.post(
            f"{BASE}/jobs/{job_id}/channel-lists/{lst['id']}/channels",
            json={"channel_number": 1, "source_label": "Kick"},
            headers=h,
        )
        fixture = await client.post(
            f"{BASE}/jobs/{job_id}/fixtures",
            json={"device_name": "Wash 1", "universe": 2, "dmx_address": 17},
            headers=h,
        )
        assert fixture.status_code == 201, fixture.text
        await client.post(
            f"{BASE}/jobs/{job_id}/graph/video-lists", json={"name": "Main"}, headers=h
        )
        token = (await client.post(f"{BASE}/jobs/{job_id}/share", headers=h)).json()["token"]

        res = await client.get(f"{BASE}/jobs/{job_id}/crew-sheets", params={"token": token})
        assert res.status_code == 200, res.text
        body = res.json()
        assert [c["source_label"] for c in body["sound"][0]["list"]["channels"]] == ["Kick"]
        assert body["sound"][0]["soft_patch"]["channels"][0]["channel_number"] == 1
        assert "fader_map" in body["sound"][0] and "console" in body["sound"][0]
        assert [(f["universe"], f["dmx_address"]) for f in body["lights"]] == [(2, 17)]
        assert [v["name"] for v in body["video"]["lists"]] == ["Main"]

        # no token, a tampered token and another job's token never open it
        assert (await client.get(f"{BASE}/jobs/{job_id}/crew-sheets")).status_code == 422
        bad = await client.get(f"{BASE}/jobs/{job_id}/crew-sheets", params={"token": token + "x"})
        assert bad.status_code == 401
        other = await client.get(f"{BASE}/jobs/{other_job}/crew-sheets", params={"token": token})
        assert other.status_code == 401
