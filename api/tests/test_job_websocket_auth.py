"""Job websocket user-token path.

The job room also admits a view-scoped crew share token (covered in
test_crew_websocket.py). This file pins down the *user* path: a token must resolve
to an existing, active account (mirroring get_current_user) before the room is
joined; a deactivated or unknown account is rejected even with a valid JWT."""

import asyncio

import pytest
from sqlalchemy import delete
from starlette.testclient import TestClient
from starlette.websockets import WebSocketDisconnect

from app.core import db as db_mod
from app.domains.auth.models import User
from app.domains.auth.security import create_access_token, hash_password
from app.main import app

WS = "/api/v1/ws/jobs"


async def _seed_user(*, active: bool) -> str:
    async with db_mod.SessionLocal() as session:
        await session.execute(delete(User))
        user = User(
            email="job@test.local",
            password_hash=hash_password("jobpass"),
            full_name="Job User",
            role="manager",
            is_active=active,
            is_admin=False,
            auth_source="local",
        )
        session.add(user)
        await session.commit()
        await session.refresh(user)
        return create_access_token(user.id, "job@test.local", "manager")


def _user_token(*, active: bool) -> str:
    # The job-websocket tests below are synchronous, so seed via a fresh loop.
    return asyncio.run(_seed_user(active=active))


def test_job_websocket_accepts_active_user_token():
    job_id = "11111111-1111-1111-1111-111111111111"

    with TestClient(app) as client:
        with client.websocket_connect(f"{WS}/{job_id}?token={_user_token(active=True)}") as ws:
            ws.send_text("ping")


def test_job_websocket_rejects_inactive_user_token():
    job_id = "11111111-1111-1111-1111-111111111111"

    with TestClient(app) as client:
        with pytest.raises(WebSocketDisconnect):
            with client.websocket_connect(f"{WS}/{job_id}?token={_user_token(active=False)}"):
                pass


def test_job_websocket_rejects_unknown_user_token():
    job_id = "11111111-1111-1111-1111-111111111111"

    with TestClient(app) as client:
        unknown = create_access_token(999999, "ghost@test.local", "manager")
        with pytest.raises(WebSocketDisconnect):
            with client.websocket_connect(f"{WS}/{job_id}?token={unknown}"):
                pass
