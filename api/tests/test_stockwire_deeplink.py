"""Outbound deeplink (Stagewire -> stockwire-rental) targets the rental *frontend*.

The deeplink used to be built from ``base_url`` (the rental API host), so it always
landed on whatever host base_url pointed at — in dev that is localhost:9000 even when the
real rental frontend lives elsewhere. It must now prefer the dedicated ``rental_frontend_url``
and only fall back to base_url when that is unset.
"""

import uuid

import pytest
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


async def _configure(rental_frontend_url):
    async with db_mod.SessionLocal() as db:
        await save_integration_config(
            db,
            enabled=True,
            base_url="http://localhost:8000",
            api_key="dev-token",
            public_url="http://stagewire:8010",
            rental_frontend_url=rental_frontend_url,
        )
        await save_deeplink_secret(db, "test-deeplink-secret")


async def _deeplink(auth_headers, job_id):
    async with _client(auth_headers) as ac:
        return await ac.get(f"{BASE}/stockwire/jobs/{job_id}/deeplink")


async def test_deeplink_uses_rental_frontend_url(auth_headers):
    job_id = await _create_job(auth_headers)
    await _set_stockwire_job_id(job_id, "rental-123")
    await _configure("https://rental.sj-tech.se")

    res = await _deeplink(auth_headers, job_id)
    assert res.status_code == 200, res.text
    url = res.json()["url"]
    assert url.startswith("https://rental.sj-tech.se" + DEEPLINK_PATH), url


async def test_deeplink_falls_back_to_base_url_when_frontend_unset(auth_headers):
    job_id = await _create_job(auth_headers)
    await _set_stockwire_job_id(job_id, "rental-456")
    await _configure("")

    res = await _deeplink(auth_headers, job_id)
    assert res.status_code == 200, res.text
    url = res.json()["url"]
    assert url.startswith("http://localhost:8000" + DEEPLINK_PATH), url


async def test_deeplink_requires_linked_job(auth_headers):
    job_id = await _create_job(auth_headers)  # no stockwire_job_id set
    await _configure("https://rental.sj-tech.se")

    res = await _deeplink(auth_headers, job_id)
    assert res.status_code == 400, res.text
