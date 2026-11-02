"""Availability endpoint: minimum Stockwire stock per product vs the job's need.

The endpoint calls ``GET /api/v1/inventory/products/{id}/availability`` on the (mocked)
Stockwire client. We inject a MockTransport through a patched client so no real upstream is
hit, and set the integration config in the test DB so the endpoint considers it configured.
"""

import uuid

import httpx
import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy import delete

from app.core import db as db_mod
from app.domains.auth.models import AppSetting
from app.domains.graph.models import GraphDevice
from app.domains.stockwire import client as sw_client_mod
from app.domains.stockwire.client import StockwireClient
from app.domains.stockwire.config import save_integration_config
from app.main import app

BASE = "/api/v1"

# product_id -> per-day available quantity returned by the mocked upstream.
AVAIL = {
    "1": {"2026-11-02": 8, "2026-11-03": 5, "2026-11-04": 8},
    "2": {"2026-11-02": 2, "2026-11-03": 1, "2026-11-04": 3},
}


def _avail_handler(request: httpx.Request) -> httpx.Response:
    if "/availability" in request.url.path:
        pid = request.url.path.split("/")[-2]
        return httpx.Response(200, json=AVAIL.get(pid, {}))
    return httpx.Response(404, json={"detail": "not found"})


class _MockStockwireClient(StockwireClient):
    """Force the mocked transport regardless of how the endpoint builds the client."""

    def __init__(self, base_url=None, token=None, transport=None):
        super().__init__(
            base_url=base_url, token=token, transport=httpx.MockTransport(_avail_handler)
        )


@pytest.fixture
def mock_stockwire(monkeypatch):
    monkeypatch.setattr(sw_client_mod, "StockwireClient", _MockStockwireClient)
    yield


@pytest.fixture
async def integration_config():
    async with db_mod.SessionLocal() as db:
        await save_integration_config(
            db, enabled=True, base_url="http://sw.test", api_key="test-key"
        )
    yield
    async with db_mod.SessionLocal() as db:
        await db.execute(delete(AppSetting).where(AppSetting.key == "stockwire_integration"))
        await db.commit()


def _device(job_id, product_id, name):
    if isinstance(job_id, str):
        job_id = uuid.UUID(job_id)
    return GraphDevice(
        job_id=job_id,
        domain="audio",
        kind="mic",
        name=name,
        stockwire_product_id=str(product_id),
        stockwire_product_name=name,
    )


async def _create_job(ac, auth_headers, start_date, end_date):
    resp = await ac.post(
        f"{BASE}/jobs",
        headers=auth_headers,
        json={"title": "Avail job", "start_date": start_date, "end_date": end_date},
    )
    assert resp.status_code == 201, resp.text
    return resp.json()["id"]


async def test_availability_reports_min_and_flags_short(
    auth_headers, mock_stockwire, integration_config
):
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        job_id = await _create_job(ac, auth_headers, "2026-11-02", "2026-11-04")
        # 1x product 1 (min avail 5) and 2x product 2 (min avail 1 -> short)
        async with db_mod.SessionLocal() as db:
            db.add(_device(job_id, 1, "SM58"))
            db.add(_device(job_id, 2, "e935"))
            db.add(_device(job_id, 2, "e935 dup"))
            await db.commit()

        resp = await ac.get(f"{BASE}/stockwire/jobs/{job_id}/availability", headers=auth_headers)
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["configured"] is True
    assert body["missing_dates"] is False
    assert body["start_date"] == "2026-11-02"
    assert body["end_date"] == "2026-11-04"

    by_pid = {i["product_id"]: i for i in body["items"]}
    assert by_pid["1"]["needed"] == 1
    assert by_pid["1"]["available_min"] == 5  # min over the three days
    assert by_pid["1"]["short"] is False
    # Two product-2 devices need 2, but only 1 is available on the worst day.
    assert by_pid["2"]["needed"] == 2
    assert by_pid["2"]["available_min"] == 1
    assert by_pid["2"]["short"] is True
    # Sorted by product name.
    assert [i["product_name"] for i in body["items"]] == ["SM58", "e935"]


async def test_availability_missing_dates(auth_headers, mock_stockwire, integration_config):
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        job_id = await _create_job(ac, auth_headers, None, None)
        async with db_mod.SessionLocal() as db:
            db.add(_device(job_id, 1, "SM58"))
            await db.commit()
        resp = await ac.get(f"{BASE}/stockwire/jobs/{job_id}/availability", headers=auth_headers)
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["configured"] is True
    assert body["missing_dates"] is True
    assert body["items"] == []


async def test_availability_not_configured(auth_headers, mock_stockwire):
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        job_id = await _create_job(ac, auth_headers, "2026-11-02", "2026-11-04")
        async with db_mod.SessionLocal() as db:
            db.add(_device(job_id, 1, "SM58"))
            await db.commit()
        resp = await ac.get(f"{BASE}/stockwire/jobs/{job_id}/availability", headers=auth_headers)
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["configured"] is False
    assert body["items"] == []
