"""Outbound deeplink (Stagewire -> stockwire-rental) targets the rental *backend*.

The deeplink opens in the browser against the rental backend's
``/api/v1/settings/integrations/stagewire/open`` endpoint (built from the configured
``base_url``). That endpoint verifies the signed token and 302-redirects to the rental
frontend job page, so no separate frontend URL setting is needed on the Stagewire side.
"""

import uuid

from httpx import ASGITransport, AsyncClient

from app.core import db as db_mod
from app.domains.audio.models import ProductionJob
from app.domains.stockwire.config import (
    save_deeplink_secret,
    save_integration_config,
)
from app.main import app

BASE = "/api/v1"
DEEPLINK_PATH = "/api/v1/settings/integrations/stagewire/open?token="


def _client(auth_headers):
    transport = ASGITransport(app=app)
    return AsyncClient(transport=transport, base_url="http://test", headers=auth_headers)


async def _create_job(auth_headers):
    async with _client(auth_headers) as ac:
        resp = await ac.post(f"{BASE}/jobs", json={"title": "Deeplink job"})
        assert resp.status_code == 201, resp.text
        return resp.json()["id"]


async def _set_stockwire_job_id(job_id, sw_job_id):
    async with db_mod.SessionLocal() as db:
        job = await db.get(ProductionJob, uuid.UUID(job_id))
        job.stockwire_job_id = sw_job_id
        await db.commit()


async def _configure():
    async with db_mod.SessionLocal() as db:
        await save_integration_config(
            db,
            enabled=True,
            base_url="https://rental-api.sj-tech.se",
            api_key="dev-token",
            public_url="http://stagewire:8010",
        )
        await save_deeplink_secret(db, "test-deeplink-secret")


async def _deeplink(auth_headers, job_id):
    async with _client(auth_headers) as ac:
        return await ac.get(f"{BASE}/stockwire/jobs/{job_id}/deeplink")


async def test_deeplink_targets_rental_backend(auth_headers):
    job_id = await _create_job(auth_headers)
    await _set_stockwire_job_id(job_id, "rental-123")
    await _configure()

    res = await _deeplink(auth_headers, job_id)
    assert res.status_code == 200, res.text
    url = res.json()["url"]
    # The browser hits the rental backend, which 302-redirects to the frontend job page.
    assert url.startswith("https://rental-api.sj-tech.se" + DEEPLINK_PATH), url


async def test_deeplink_requires_linked_job(auth_headers):
    job_id = await _create_job(auth_headers)  # no stockwire_job_id set
    await _configure()

    res = await _deeplink(auth_headers, job_id)
    assert res.status_code == 400, res.text
