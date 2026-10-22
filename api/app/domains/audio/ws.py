import json

from fastapi import APIRouter, WebSocket, WebSocketDisconnect
from jwt import PyJWTError as JWTError

from app.domains.auth.security import decode_token

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


async def publish_job_event(job_id, event_type: str, payload) -> None:
    """Broadcast a realtime event to all clients viewing the given job.

    In-process only: with multiple API workers a shared pub/sub (e.g. Valkey)
    would be required to fan out across workers.
    """
    if hasattr(payload, "model_dump"):
        payload = payload.model_dump(mode="json")
    await manager.broadcast(str(job_id), {"type": event_type, "payload": payload})


@router.websocket("/ws/jobs/{job_id}")
async def job_ws(websocket: WebSocket, job_id: str) -> None:
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
    await manager.connect(websocket, job_id)
    try:
        while True:
            await websocket.receive_text()
    except WebSocketDisconnect:
        pass
    finally:
        manager.disconnect(websocket, job_id)
