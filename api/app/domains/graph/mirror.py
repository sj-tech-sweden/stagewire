import logging
from collections.abc import Awaitable, Callable
from uuid import UUID

from fastapi import Request, Response
from fastapi.routing import APIRoute

from app.core import db as db_mod
from app.domains.audio.models import ProductionJob
from app.domains.graph.backfill import backfill_job

logger = logging.getLogger(__name__)

WRITE_METHODS = {"POST", "PATCH", "PUT", "DELETE"}


async def sync_job_to_graph(job_id: UUID) -> None:
    """Bring the graph up to date with a job's legacy rows (own session, never raises)."""
    try:
        async with db_mod.SessionLocal() as db:
            if await db.get(ProductionJob, job_id) is None:
                return
            await backfill_job(db, job_id)
    except Exception:  # noqa: BLE001 - the legacy write already succeeded; the next read heals
        logger.exception("graph sync failed for job %s", job_id)


class MirrorToGraphRoute(APIRoute):
    """After a successful legacy write under /jobs/{job_id}/..., sync that job into the graph."""

    def get_route_handler(self) -> Callable[[Request], Awaitable[Response]]:
        original = super().get_route_handler()

        async def handler(request: Request) -> Response:
            response = await original(request)
            raw = request.path_params.get("job_id")
            if raw and request.method in WRITE_METHODS and response.status_code < 300:
                try:
                    job_id = UUID(str(raw))
                except ValueError:
                    return response
                await sync_job_to_graph(job_id)
            return response

        return handler
