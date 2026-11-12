"""The read-only crew (share) view holds only a view-scoped share token, never a user session,
so the job websocket must admit that token read-only and reject anything else."""

import pytest
from starlette.testclient import TestClient
from starlette.websockets import WebSocketDisconnect

from app.domains.auth.security import create_share_token
from app.main import app

WS = "/api/v1/ws/jobs"


def test_crew_websocket_accepts_view_token_and_rejects_garbage():
    job_id = "11111111-1111-1111-1111-111111111111"
    token = create_share_token(job_id)

    with TestClient(app) as client:
        # A valid, view-scoped share token for this job is admitted.
        with client.websocket_connect(f"{WS}/{job_id}?token={token}") as ws:
            ws.send_text("ping")  # connection stays open; no immediate close

        # A token that isn't a valid JWT (or isn't view-scoped for this job) is closed.
        with pytest.raises(WebSocketDisconnect):
            with client.websocket_connect(f"{WS}/{job_id}?token=not-a-real-token"):
                pass

        # A token minted for a *different* job is rejected even if otherwise valid.
        other = create_share_token("22222222-2222-2222-2222-222222222222")
        with pytest.raises(WebSocketDisconnect):
            with client.websocket_connect(f"{WS}/{job_id}?token={other}"):
                pass
