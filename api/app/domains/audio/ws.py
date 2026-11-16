import json
import logging
import uuid

from fastapi import APIRouter, Depends, WebSocket, WebSocketDisconnect
from jwt import PyJWTError as JWTError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.core.db import get_db
from app.core.realtime_bus import RealtimeBus
from app.domains.auth.models import User
from app.domains.auth.security import decode_token, verify_share_token

logger = logging.getLogger(__name__)

router = APIRouter()

# Per-process identity stamped on every pub/sub envelope so a worker ignores the
# messages it published itself (it already delivered those locally).
SENDER_ID = uuid.uuid4().hex

# Cross-worker fan-out bridge. Disabled in the test environment (no Valkey, and the
# pytest suite exercises the in-process path only) so it never touches the network
# during tests. In every other environment it publishes to, and subscribes from, the
# shared Valkey channel; if Valkey is unreachable it degrades to in-process only.
realtime_bus = RealtimeBus(
    get_settings().redis_url,
    SENDER_ID,
    enabled=get_settings().app_env != "test",
)


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
        # The publish path is best-effort (AGENTS.md §11, realtime_bus): a mutation
        # must never 500 because its realtime event failed to serialize. Guard the
        # serialization so a non-JSON-serializable payload is skipped (with a warning)
        # instead of propagating and aborting the originating write.
        try:
            data = json.dumps(message)
        except (TypeError, ValueError):
            logger.warning("realtime message for %s is not JSON serializable; skipping", job_id)
            return
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

    Delivered locally (in-process) and, when a Valkey bridge is active, published to
    the shared channel so other API workers forward it to their own connected clients.
    """
    if hasattr(payload, "model_dump"):
        payload = payload.model_dump(mode="json")
    message = {"type": event_type, "payload": payload}
    await manager.broadcast(str(job_id), message)
    await realtime_bus.publish("job", str(job_id), message)


async def publish_venue_event(venue_id, event_type: str, payload) -> None:
    """Broadcast a realtime event to all clients editing the given venue base rig.

    Mirrors :func:`publish_job_event` for the venue scope (a venue base-rig device
    mirrored into NetBox carries ``stagewire_venue_id``, not ``stagewire_job_id``, so
    NetBox events resolve to this room instead of a job room).
    """
    if hasattr(payload, "model_dump"):
        payload = payload.model_dump(mode="json")
    message = {"type": event_type, "payload": payload}
    await venue_manager.broadcast(str(venue_id), message)
    await realtime_bus.publish("venue", str(venue_id), message)


async def deliver_cross_worker(envelope: dict) -> None:
    """Forward a pub/sub envelope (from another worker) into our local rooms.

    Ignores envelopes we published ourselves via ``sender_id`` to avoid echo, and
    routes by scope to the matching in-process room manager.
    """
    if envelope.get("sender_id") == SENDER_ID:
        return
    scope = envelope.get("scope")
    scope_id = envelope.get("scope_id")
    message = envelope.get("message")
    if not scope_id or not message:
        return
    if scope == "job":
        await manager.broadcast(str(scope_id), message)
    elif scope == "venue":
        await venue_manager.broadcast(str(scope_id), message)


async def start_realtime_bus() -> None:
    """Start the cross-worker subscriber. No-op in the test environment."""
    await realtime_bus.start(deliver_cross_worker)


async def stop_realtime_bus() -> None:
    """Stop the cross-worker subscriber and close the Valkey client."""
    await realtime_bus.stop()


@router.websocket("/ws/jobs/{job_id}")
async def job_ws(websocket: WebSocket, job_id: str, db: AsyncSession = Depends(get_db)) -> None:
    token = websocket.query_params.get("token")
    user_id = None
    share_job_id = None
    if token:
        # Mirror get_current_user: a user JWT is only admitted if the account exists and
        # is active. Without this check a revoked/deactivated account holding a still-valid
        # JWT could open the realtime room (REST would reject it) and receive every event
        # for the job. We resolve the account here rather than trusting the token alone.
        try:
            payload = decode_token(token)
            candidate = await db.get(User, int(payload["sub"]))
            if candidate is not None and candidate.is_active:
                user_id = candidate.id
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
async def venue_ws(websocket: WebSocket, venue_id: str, db: AsyncSession = Depends(get_db)) -> None:
    # Venues are edited by authenticated users (no crew share-token fallback; the venue
    # base rig is admin workspace, not the day-of-show crew view). Admit a token only if it
    # resolves to an existing, active account — mirroring get_current_user so a revoked
    # account cannot open the room.
    token = websocket.query_params.get("token")
    user_id = None
    if token:
        try:
            payload = decode_token(token)
            candidate = await db.get(User, int(payload["sub"]))
            if candidate is not None and candidate.is_active:
                user_id = candidate.id
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
