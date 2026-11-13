"""ASGI middleware: open a history recorder around every write request, store it on success."""

from __future__ import annotations

from jwt import PyJWTError as JWTError

from app.domains.auth.security import decode_token
from app.domains.history import recorder, service

SAFE_METHODS = {"GET", "HEAD", "OPTIONS"}


def _actor(scope: dict) -> int | None:
    for key, value in scope.get("headers") or []:
        if key == b"authorization" and value.lower().startswith(b"bearer "):
            try:
                return int(decode_token(value[7:].decode())["sub"])
            except (JWTError, KeyError, ValueError):
                return None
    return None


class HistoryMiddleware:
    def __init__(self, app):
        self.app = app

    async def __call__(self, scope, receive, send):
        path = scope.get("path", "")
        if (
            scope["type"] != "http"
            or scope["method"] in SAFE_METHODS
            or not path.startswith("/api/v1/")
            or "/history" in path  # undo / redo / restore must not record themselves
        ):
            await self.app(scope, receive, send)
            return
        rec, token = recorder.start()
        # The response is held back until the history entry is stored. Otherwise a client that
        # undoes right after a write could run before its entry exists and undo the wrong step.
        # Only JSON bodies are held (every data write answers with one); an export, a download or a
        # stream passes straight through and is recorded afterwards.
        held: list[dict] = []
        holding = {"on": True}
        status_code = {"value": 500}

        async def send_wrapper(message):
            if message["type"] == "http.response.start":
                status_code["value"] = message["status"]
                content_type = dict(message.get("headers") or []).get(b"content-type", b"")
                holding["on"] = content_type.startswith(b"application/json")
            if holding["on"]:
                held.append(message)
            else:
                await send(message)

        try:
            await self.app(scope, receive, send_wrapper)
        finally:
            recorder.stop(token)
            try:
                if status_code["value"] < 400 and rec.changes:
                    route = scope.get("route")
                    name = getattr(route, "name", None) or getattr(
                        scope.get("endpoint"), "__name__", ""
                    )
                    await service.record(rec, _actor(scope), service.humanize(name))
            except Exception:  # noqa: BLE001 - history must never break the write that succeeded
                import logging

                logging.getLogger(__name__).exception("could not record history")
            for message in held:
                await send(message)
