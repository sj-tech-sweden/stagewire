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
from app.domains.audio.schemas import ProductionJobRead
from app.domains.auth.deps import get_current_user
from app.domains.auth.security import create_share_token, verify_share_token
from app.domains.graph.router import read_job_graph

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
    locale: str | None = Query(
        None,
        description="Display locale the crew link should open in (e.g. 'en', 'sv'). "
        "Embeds in the token so the link carries its own language.",
    ),
):
    """Mint a read-only share token for the day-of-show mobile view.

    Requires a normal user session — you must be logged in to hand out a link — but the
    resulting token grants view-only access with no login. The creator's current UI
    locale is embedded so a crew member opens the link in that language.
    """
    if await db.get(ProductionJob, job_id) is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Job not found")
    token = create_share_token(job_id, ttl_minutes=ttl_minutes, locale=locale)
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

    graph = await read_job_graph(db, job_id)
    # The full job carries the stage/venue geometry the crew view redraws as the same stage frame
    # the workspace canvas uses, so the read-only map looks and feels identical to the editor.
    # The token's locale is echoed so the read-only view can apply it before it renders (the link
    # itself carries the language; there is no user session to derive one from).
    return {
        "job": ProductionJobRead.model_validate(job).model_dump(mode="json"),
        "graph": graph.model_dump(mode="json"),
        "locale": claims.get("locale"),
    }
