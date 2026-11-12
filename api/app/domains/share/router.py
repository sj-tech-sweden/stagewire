"""Job-scoped, login-free sharing for the day-of-show crew mobile view.

A logged-in user mints a share token (``POST /jobs/{job_id}/share``); the token is a
signed JWT carrying the job id and a ``view`` scope. Asset assignment is an optional,
explicit capability on the token; all other share-view behavior remains read-only.
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
from app.domains.graph import schemas as graph_schemas
from app.domains.graph.models import GraphDevice
from app.domains.graph.router import (
    bind_asset_for_job,
    read_job_graph,
    unbind_asset_for_job,
)
from app.domains.stockwire.router import _catalog_client

router = APIRouter(prefix="/jobs/{job_id}", tags=["share"])
SHARED_ASSET_FIELDS = (
    "id",
    "product_id",
    "asset_tag",
    "serial_number",
    "barcode",
    "qr_code",
    "rfid",
    "description",
    "name",
)


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
    allow_asset_binding: bool = Query(
        False,
        description=(
            "Allow anyone with the share link to bind or unbind Stockwire assets for this job."
        ),
    ),
):
    """Mint a share token, optionally allowing job-scoped Stockwire asset assignment.

    Requires a normal user session. Links remain view-only unless asset binding is explicitly
    enabled; the creator's current UI locale is embedded so the link carries its own language.
    """
    if await db.get(ProductionJob, job_id) is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Job not found")
    token = create_share_token(
        job_id,
        ttl_minutes=ttl_minutes,
        locale=locale,
        can_bind_assets=allow_asset_binding,
    )
    return {"token": token}


@router.get("/mobile-view")
async def mobile_view(
    job_id: UUID,
    token: str = Query(..., description="Share token from POST /jobs/{job_id}/share"),
    db: AsyncSession = Depends(get_db),
):
    """Crew projection, with asset writes enabled only by an explicitly scoped token.

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
        "can_bind_assets": claims.get("can_bind_assets") is True,
    }


def _authorize_asset_binding(token: str, job_id: UUID) -> None:
    try:
        claims = verify_share_token(token)
    except ValueError as exc:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, str(exc)) from exc
    if str(claims.get("job_id")) != str(job_id):
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Token is for a different job")
    if claims.get("can_bind_assets") is not True:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Share token cannot bind Stockwire assets")


@router.post("/devices/{device_id}/bind-asset", response_model=graph_schemas.GraphDeviceRead)
async def bind_shared_asset(
    job_id: UUID,
    device_id: UUID,
    payload: graph_schemas.AssetBind,
    token: str = Query(..., description="Share token with asset-binding permission"),
    db: AsyncSession = Depends(get_db),
) -> dict:
    _authorize_asset_binding(token, job_id)
    return await bind_asset_for_job(db, job_id, device_id, payload, payload.expected_revision)


@router.get("/devices/{device_id}/stockwire-assets")
async def shared_product_assets(
    job_id: UUID,
    device_id: UUID,
    token: str = Query(..., description="Share token with asset-binding permission"),
    db: AsyncSession = Depends(get_db),
) -> dict:
    _authorize_asset_binding(token, job_id)
    device = await db.get(GraphDevice, device_id)
    if device is None or device.job_id != job_id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Device not found")
    if not device.stockwire_product_id:
        return {"items": []}
    sw = await _catalog_client(db)
    if sw is None:
        return {"items": []}
    try:
        assets = await sw.list_product_devices(device.stockwire_product_id)
        return {
            "items": [
                {key: asset[key] for key in SHARED_ASSET_FIELDS if key in asset} for asset in assets
            ]
        }
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(
            status.HTTP_502_BAD_GATEWAY,
            f"Stockwire upstream error: {type(exc).__name__}: {exc}",
        ) from exc


@router.delete("/devices/{device_id}/asset-binding", response_model=graph_schemas.GraphDeviceRead)
async def unbind_shared_asset(
    job_id: UUID,
    device_id: UUID,
    token: str = Query(..., description="Share token with asset-binding permission"),
    expected_revision: int = Query(..., ge=1),
    db: AsyncSession = Depends(get_db),
) -> dict:
    _authorize_asset_binding(token, job_id)
    return await unbind_asset_for_job(db, job_id, device_id, expected_revision)
