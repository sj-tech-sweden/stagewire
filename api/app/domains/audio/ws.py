import json

from fastapi import APIRouter, WebSocket, WebSocketDisconnect
from jwt import PyJWTError as JWTError

from app.domains.auth.security import decode_token, verify_share_token

router = APIRouter()


class ConnectionManager:
    def __init__(self) -> None:
        self.rooms: dict[str, set[WebSocket]] = {}

    async def connect(self, websocket: WebSocket, job_id: str) -> None:
        self.rooms.setdefault(job_id, set()).add(websocket)

    def disconnect(self, websocket: WebSocket, job_id: str) -> None:
        room = self.rooms.get(job_id)
        if room:
            room.discard(websocket)
            if not room:
                self.rooms.pop(job_id, None)

    async def broadcast(self, job_id: str, message: dict) -> None:
        room = self.rooms.get(job_id)
        if not room:
            return
        data = json.dumps(message)
        stale: list[WebSocket] = []
        for websocket in list(room):
            try:
                await websocket.send_text(data)
            except Exception:
                stale.append(websocket)
        for websocket in stale:
            self.disconnect(websocket, job_id)


manager = ConnectionManager()

# Venue base-rig editing reuses the same realtime shape as jobs. A venue rig is
# edited by admins in the venue workspace, so it gets its own room keyed by venue id
# (no share-token fallback — venues are not shared with the crew mobile view).
venue_manager = ConnectionManager()


async def publish_job_event(job_id, event_type: str, payload) -> None:
    """Broadcast a realtime event to all clients viewing the given job.

    In-process only: with multiple API workers a shared pub/sub (e.g. Valkey)
    would be required to fan out across workers.
    """
    if hasattr(payload, "model_dump"):
        payload = payload.model_dump(mode="json")
    await manager.broadcast(str(job_id), {"type": event_type, "payload": payload})


async def publish_venue_event(venue_id, event_type: str, payload) -> None:
    """Broadcast a realtime event to all clients editing the given venue base rig.

    Mirrors :func:`publish_job_event` for the venue scope (a venue base-rig device
    mirrored into NetBox carries ``stagewire_venue_id``, not ``stagewire_job_id``, so
    NetBox events resolve to this room instead of a job room).
    """
    if hasattr(payload, "model_dump"):
        payload = payload.model_dump(mode="json")
    await venue_manager.broadcast(str(venue_id), {"type": event_type, "payload": payload})


@router.websocket("/ws/jobs/{job_id}")
async def job_ws(websocket: WebSocket, job_id: str) -> None:
    token = websocket.query_params.get("token")
    user_id = None
    share_job_id = None
    if token:
        try:
            user_id = int(decode_token(token)["sub"])
        except (JWTError, KeyError, ValueError):
            user_id = None
        # A logged-in session was not found — fall back to a read-only, view-scoped share token
        # (used by the day-of-show crew mobile view, which has no user session).
        if user_id is None:
            try:
                claims = verify_share_token(token)
            except ValueError:
                claims = None
            if claims is not None and str(claims.get("job_id")) == str(job_id):
                share_job_id = claims.get("job_id")
    if user_id is None and share_job_id is None:
        await websocket.close(code=1008)
        return

    await websocket.accept()
    await manager.connect(websocket, job_id)
    try:
        while True:
            await websocket.receive_text()
    except WebSocketDisconnect:
        pass
    finally:
        manager.disconnect(websocket, job_id)


@router.websocket("/ws/venues/{venue_id}")
async def venue_ws(websocket: WebSocket, venue_id: str) -> None:
    # Venues are edited by authenticated admins only (no crew share-token fallback).
    token = websocket.query_params.get("token")
    user_id = None
    if token:
        try:
            user_id = int(decode_token(token)["sub"])
        except (JWTError, KeyError, ValueError):
            user_id = None
    if user_id is None:
        await websocket.close(code=1008)
        return

    await websocket.accept()
    await venue_manager.connect(websocket, venue_id)
    try:
        while True:
            await websocket.receive_text()
    except WebSocketDisconnect:
        pass
    finally:
        venue_manager.disconnect(websocket, venue_id)
