"""The venue base-rig editor is admin-only, so the venue websocket must admit a valid
user JWT and reject anything else (there is no crew share-token fallback, unlike jobs)."""

import pytest
from starlette.testclient import TestClient
from starlette.websockets import WebSocketDisconnect

from app.domains.auth.security import create_access_token
from app.main import app

WS = "/api/v1/ws/venues"


def _user_token() -> str:
    # Venues are edited by authenticated admins only.
    return create_access_token(1, "admin@test.local", "admin")


def test_venue_websocket_accepts_user_token_and_rejects_garbage():
    venue_id = "33333333-3333-3333-3333-333333333333"
    token = _user_token()

    with TestClient(app) as client:
        # A valid user JWT is admitted and the connection stays open.
        with client.websocket_connect(f"{WS}/{venue_id}?token={token}") as ws:
            ws.send_text("ping")

        # A token that isn't a valid JWT is closed immediately.
        with pytest.raises(WebSocketDisconnect):
            with client.websocket_connect(f"{WS}/{venue_id}?token=not-a-real-token"):
                pass
