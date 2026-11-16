"""Cross-worker realtime fan-out over Valkey (Redis protocol).

The websocket rooms in ``app.domains.audio.ws`` are in-process only: an event
published on one API worker is not delivered to clients connected to another worker.
This module bridges workers with a single Valkey pub/sub channel. Every worker
publishes every event to the channel and runs a subscriber that forwards inbound
messages to its own in-process rooms.

Design notes:

* A per-process ``sender_id`` is stamped on every envelope so a worker ignores the
  messages it published itself (it already delivered them locally), preventing echo.
* The channel is global; the envelope carries ``scope`` (``"job"``/``"venue"``) and
  ``scope_id`` so each worker only forwards to rooms it actually has members for.
* Everything is best-effort. If Valkey is unavailable, the publish is a no-op and the
  subscriber retries in the background; the in-process broadcast keeps single-worker
  and local-dev behaviour intact. This is what makes the layer safe to ship before a
  Valkey dependency is guaranteed in every environment.
"""

from __future__ import annotations

import asyncio
import json
import logging

logger = logging.getLogger("stagewire.realtime")

CHANNEL = "stagewire:realtime"


class RealtimeBus:
    def __init__(self, redis_url: str | None, sender_id: str, enabled: bool = True) -> None:
        self.sender_id = sender_id
        self._task: asyncio.Task | None = None
        self._client = None
        if enabled and redis_url:
            try:
                from redis import asyncio as redis_asyncio

                self._client = redis_asyncio.Redis.from_url(redis_url, decode_responses=True)
            except ImportError:
                # The redis client is optional; without it we fall back to in-process only.
                logger.warning("redis client not installed; realtime fan-out disabled (local only)")
                self._client = None
            except Exception:  # noqa: BLE001 - never block startup on a bad URL
                logger.warning("redis client creation failed; fan-out disabled", exc_info=True)
                self._client = None

    @property
    def enabled(self) -> bool:
        return self._client is not None

    async def publish(self, scope: str, scope_id: str, message: dict) -> None:
        """Publish an event envelope to Valkey. Best-effort; never raises."""
        if self._client is None:
            return
        envelope = {
            "sender_id": self.sender_id,
            "scope": scope,
            "scope_id": scope_id,
            "message": message,
        }
        try:
            await self._client.publish(CHANNEL, json.dumps(envelope))
        except Exception:  # noqa: BLE001 - fan-out must not fail the originating write
            logger.warning("realtime publish failed", exc_info=True)

    async def run(self, on_message) -> None:
        """Subscribe loop. Retries with backoff if Valkey drops. Intended to run as a task."""
        if self._client is None:
            return
        while True:
            try:
                pubsub = self._client.pubsub()
                await pubsub.subscribe(CHANNEL)
                async for raw in pubsub.listen():
                    if raw is None or raw.get("type") != "message" or raw.get("data") is None:
                        continue
                    try:
                        envelope = json.loads(raw["data"])
                    except (ValueError, TypeError):
                        continue
                    try:
                        await on_message(envelope)
                    except Exception:  # noqa: BLE001 - one bad message must not kill the loop
                        logger.exception("realtime on_message failed")
            except asyncio.CancelledError:
                raise
            except Exception:  # noqa: BLE001 - reconnect on any transport error
                logger.warning("realtime subscriber disconnected; retrying in 2s", exc_info=True)
                await asyncio.sleep(2)

    async def start(self, on_message) -> None:
        if self._task is not None or self._client is None:
            return
        self._task = asyncio.create_task(self.run(on_message))

    async def stop(self) -> None:
        task = self._task
        self._task = None
        if task is not None:
            task.cancel()
            try:
                await task
            except (asyncio.CancelledError, Exception):  # noqa: BLE001
                pass
        if self._client is not None:
            try:
                await self._client.close()
            except Exception:  # noqa: BLE001
                pass
