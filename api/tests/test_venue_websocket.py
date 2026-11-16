"""The venue base-rig editor is authenticated-user only (no crew share-token fallback,
unlike jobs). The websocket must admit a token that resolves to an existing, active
account and reject everything else — matching ``get_current_user``."""

import asyncio

import pytest
from sqlalchemy import delete
from starlette.testclient import TestClient
from starlette.websockets import WebSocketDisconnect

from app.core import db as db_mod
from app.domains.auth.models import User
from app.domains.auth.security import create_access_token, hash_password
from app.main import app

WS = "/api/v1/ws/venues"


async def _seed_user(*, active: bool) -> str:
    async with db_mod.SessionLocal() as session:
        await session.execute(delete(User))
        user = User(
            email="venue@test.local",
            password_hash=hash_password("venpass"),
            full_name="Venue User",
            role="admin",
            is_active=active,
            is_admin=True,
            auth_source="local",
        )
        session.add(user)
        await session.commit()
        await session.refresh(user)
        return create_access_token(user.id, "venue@test.local", "admin")


def _token_for(*, active: bool) -> str:
    # Tests here are synchronous, so seed via a fresh event loop.
    return asyncio.run(_seed_user(active=active))


def test_venue_websocket_accepts_active_user_token_and_rejects_garbage():
    venue_id = "33333333-3333-3333-3333-333333333333"
    token = _token_for(active=True)

    with TestClient(app) as client:
        # A valid token for an existing, active account is admitted and stays open.
        with client.websocket_connect(f"{WS}/{venue_id}?token={token}") as ws:
            ws.send_text("ping")

        # A token that isn't a valid JWT is closed immediately.
        with pytest.raises(WebSocketDisconnect):
            with client.websocket_connect(f"{WS}/{venue_id}?token=not-a-real-token"):
                pass


def test_venue_websocket_rejects_inactive_or_unknown_user():
    venue_id = "33333333-3333-3333-3333-333333333333"

    with TestClient(app) as client:
        # An existing but deactivated account is rejected even with a valid JWT.
        inactive = _token_for(active=False)
        with pytest.raises(WebSocketDisconnect):
            with client.websocket_connect(f"{WS}/{venue_id}?token={inactive}"):
                pass

        # A token whose sub does not match any account is rejected.
        unknown = create_access_token(999999, "ghost@test.local", "admin")
        with pytest.raises(WebSocketDisconnect):
            with client.websocket_connect(f"{WS}/{venue_id}?token={unknown}"):
                pass
