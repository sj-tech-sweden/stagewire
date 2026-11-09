"""Read-only, login-free sharing for the day-of-show crew mobile view.

A logged-in user mints a share token (``POST /jobs/{job_id}/share``); the token is a
signed JWT carrying only the job id and a ``view`` scope. A crew member then opens
``GET /jobs/{job_id}/mobile-view?token=...`` with no session and receives a read-only
projection of the job. No write path is exposed through this router.
"""

from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.db import get_db
from app.domains.audio.models import ProductionJob
from app.domains.auth.deps import get_current_user
from app.domains.auth.security import create_share_token, verify_share_token
from app.domains.graph import schemas
from app.domains.graph.router import _all_devices, _all_edges, _require_job

router = APIRouter(prefix="/jobs/{job_id}", tags=["share"])


@router.post("/share", status_code=200)
async def create_share_link(
    job_id: UUID,
    db: AsyncSession = Depends(get_db),
    _user=Depends(get_current_user),
    ttl_minutes: int | None = Query(
        None,
        ge=0,
        le=60 * 24 * 30,
        description="Token lifetime in minutes; 0 = never expires. Omit to use the server default.",
    ),
):
    """Mint a read-only share token for the day-of-show mobile view.

    Requires a normal user session — you must be logged in to hand out a link — but the
    resulting token grants view-only access with no login.
    """
    await _require_job(db, job_id)
    token = create_share_token(job_id, ttl_minutes=ttl_minutes)
    return {"token": token}


@router.get("/mobile-view")
async def mobile_view(
    job_id: UUID,
    token: str = Query(..., description="Share token from POST /jobs/{job_id}/share"),
    db: AsyncSession = Depends(get_db),
):
    """Read-only day-of-show projection for the crew mobile view.

    Authenticated solely by the share token; no user session is required.
    """
    try:
        claims = verify_share_token(token)
    except ValueError as exc:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, str(exc)) from exc
    if str(claims.get("job_id")) != str(job_id):
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Token is for a different job")

    job = await db.get(ProductionJob, job_id)
    if job is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Job not found")

    graph = schemas.GraphRead(
        devices=[schemas.GraphDeviceRead.model_validate(d) for d in await _all_devices(db, job_id)],
        edges=[schemas.ConnectionEdgeRead.model_validate(e) for e in await _all_edges(db, job_id)],
    )
    return {
        "job": {"id": str(job.id), "title": job.title},
        "graph": graph.model_dump(mode="json"),
    }
