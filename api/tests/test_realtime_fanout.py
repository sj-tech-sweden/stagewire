"""Cross-worker realtime fan-out (Valkey pub/sub) logic.

These tests exercise the parts that don't require a running Valkey:

* ``publish_job_event`` / ``publish_venue_event`` still deliver locally via the
  in-process room manager (the bus is disabled in the test environment, so no
  network call happens).
* ``deliver_cross_worker`` routes a foreign envelope to the correct manager, ignores
  envelopes published by this worker (echo guard), and drops malformed envelopes.
"""

import pytest

from app.domains.audio import ws as ws_mod


class _StubManager:
    def __init__(self) -> None:
        self.calls: list[tuple[str, dict]] = []

    async def broadcast(self, scope_id: str, message: dict) -> None:
        self.calls.append((scope_id, message))


@pytest.fixture
def managers(monkeypatch):
    job = _StubManager()
    venue = _StubManager()
    monkeypatch.setattr(ws_mod, "manager", job)
    monkeypatch.setattr(ws_mod, "venue_manager", venue)
    return job, venue


@pytest.mark.asyncio
async def test_publish_job_event_broadcasts_locally(managers):
    job_mgr, _ = managers
    await ws_mod.publish_job_event("job-1", "graph.device.upsert", {"id": "d1"})

    assert job_mgr.calls == [("job-1", {"type": "graph.device.upsert", "payload": {"id": "d1"}})]
    # In the test environment the Valkey bridge is disabled, so fan-out is a no-op.
    assert ws_mod.realtime_bus.enabled is False


@pytest.mark.asyncio
async def test_publish_venue_event_broadcasts_locally(managers):
    _, venue_mgr = managers
    await ws_mod.publish_venue_event("v-1", "graph.device.netbox", {"id": "d2"})

    assert venue_mgr.calls == [("v-1", {"type": "graph.device.netbox", "payload": {"id": "d2"}})]


@pytest.mark.asyncio
async def test_deliver_cross_worker_routes_and_skips_self(managers):
    job_mgr, venue_mgr = managers

    # A foreign worker's job envelope is forwarded to the job room manager.
    await ws_mod.deliver_cross_worker(
        {
            "sender_id": "other-worker",
            "scope": "job",
            "scope_id": "job-9",
            "message": {"type": "x", "payload": {}},
        }
    )
    assert job_mgr.calls == [("job-9", {"type": "x", "payload": {}})]
    assert venue_mgr.calls == []

    # An envelope we published ourselves must be ignored (would otherwise echo).
    await ws_mod.deliver_cross_worker(
        {
            "sender_id": ws_mod.SENDER_ID,
            "scope": "job",
            "scope_id": "job-9",
            "message": {"type": "x", "payload": {}},
        }
    )
    assert job_mgr.calls == [("job-9", {"type": "x", "payload": {}})]  # unchanged

    # A venue envelope is forwarded to the venue room manager.
    await ws_mod.deliver_cross_worker(
        {
            "sender_id": "other-worker",
            "scope": "venue",
            "scope_id": "v-9",
            "message": {"type": "y", "payload": {}},
        }
    )
    assert venue_mgr.calls == [("v-9", {"type": "y", "payload": {}})]

    # A malformed envelope (missing scope_id/message) is dropped, not forwarded.
    await ws_mod.deliver_cross_worker({"scope": "job"})
    assert job_mgr.calls == [("job-9", {"type": "x", "payload": {}})]
    assert venue_mgr.calls == [("v-9", {"type": "y", "payload": {}})]
