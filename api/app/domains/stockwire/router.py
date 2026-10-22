from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.responses import RedirectResponse
from pydantic import BaseModel
from sqlalchemy import select

from app.core.config import get_settings
from app.core.db import get_db
from app.domains.audio.models import ProductionJob
from app.domains.auth.deps import get_current_user
from app.domains.stockwire import client, schemas
from app.domains.stockwire.config import (
    STAGEWIRE_RENTAL_INSTANCE_ID,
    load_integration_config,
)
from app.domains.stockwire.deeplink import sign_deeplink, verify_deeplink

router = APIRouter(
    prefix="/stockwire", tags=["stockwire"], dependencies=[Depends(get_current_user)]
)

public_router = APIRouter(prefix="/stockwire", tags=["stockwire"])


async def _stockwire_client(db) -> client.StockwireClient:
    cfg = await load_integration_config(db)
    return client.StockwireClient(base_url=cfg["base_url"], token=cfg["api_key"])


@router.get("/jobs/{job_id}")
async def get_job(job_id: str, db=Depends(get_db)) -> dict:
    try:
        sw = await _stockwire_client(db)
        return await sw.get_job(job_id)
    except Exception as exc:  # noqa: BLE001 - surface upstream errors to caller
        detail = f"Stockwire upstream error: {type(exc).__name__}: {exc}"
        raise HTTPException(status.HTTP_502_BAD_GATEWAY, detail) from exc


@router.get("/products")
async def search_products(
    search: str | None = None,
    category: str | None = None,
    category_id: int | None = None,
    brand: str | None = None,
    manufacturer: str | None = None,
    exclude_rental: bool = False,
    min_inputs: int | None = None,
    min_outputs: int | None = None,
    skip: int = 0,
    limit: int = 50,
    db=Depends(get_db),
) -> dict:
    try:
        sw = await _stockwire_client(db)
        return await sw.search_products(
            search=search,
            category=category,
            category_id=category_id,
            brand=brand,
            manufacturer=manufacturer,
            exclude_rental=exclude_rental,
            min_inputs=min_inputs,
            min_outputs=min_outputs,
            skip=skip,
            limit=limit,
        )
    except Exception as exc:  # noqa: BLE001
        detail = f"Stockwire upstream error: {type(exc).__name__}: {exc}"
        raise HTTPException(status.HTTP_502_BAD_GATEWAY, detail) from exc


@router.get("/products/{product_id}")
async def get_product(product_id: int | str, db=Depends(get_db)) -> dict:
    try:
        sw = await _stockwire_client(db)
        return await sw.get_product(product_id)
    except Exception as exc:  # noqa: BLE001
        detail = f"Stockwire upstream error: {type(exc).__name__}: {exc}"
        raise HTTPException(status.HTTP_502_BAD_GATEWAY, detail) from exc


@router.get("/categories")
async def list_categories(db=Depends(get_db)) -> dict:
    try:
        sw = await _stockwire_client(db)
        return {"categories": await sw.list_categories()}
    except Exception as exc:  # noqa: BLE001
        detail = f"Stockwire upstream error: {type(exc).__name__}: {exc}"
        raise HTTPException(status.HTTP_502_BAD_GATEWAY, detail) from exc


@router.post("/jobs/{job_id}/request-additions", status_code=202)
async def request_additions(
    job_id: str, payload: schemas.StockwireRequestAdditions, db=Depends(get_db)
):
    try:
        sw = await _stockwire_client(db)
        return await sw.request_additions(job_id, [item.model_dump() for item in payload.items])
    except Exception as exc:  # noqa: BLE001
        detail = f"Stockwire upstream error: {type(exc).__name__}: {exc}"
        raise HTTPException(status.HTTP_502_BAD_GATEWAY, detail) from exc


@public_router.get("/deeplink/job")
async def deeplink_resolve_job(token: str, db=Depends(get_db)):
    """Deeplink from stockwire-rental → opens the linked Stagewire job.

    The token carries the stockwire-rental job id. If no Stagewire job is linked to
    it yet, one is created from the rental job's details.
    """
    cfg = await load_integration_config(db)
    secret = cfg.get("deeplink_secret")
    if not secret:
        raise HTTPException(
            status.HTTP_400_BAD_REQUEST, "Connect stockwire-rental first (deeplinks are not set up)"
        )
    try:
        payload = verify_deeplink(secret, token)
    except ValueError as exc:
        raise HTTPException(
            status.HTTP_400_BAD_REQUEST, "Invalid or expired deeplink token"
        ) from exc
    if payload.get("src") != "stockwire":
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Invalid deeplink source")

    raw = str(payload.get("job_id") or "").strip()
    web = get_settings().effective_frontend_base_url.rstrip("/")
    try:
        as_uuid = UUID(raw)
    except ValueError:
        as_uuid = None
    if as_uuid is not None:
        existing = await db.get(ProductionJob, as_uuid)
        if existing is not None:
            return RedirectResponse(url=f"{web}/jobs/{existing.id}")

    result = await db.execute(select(ProductionJob).where(ProductionJob.stockwire_job_id == raw))
    job = result.scalars().first()
    if job is None:
        sw = client.StockwireClient(base_url=cfg["base_url"], token=cfg["api_key"])
        try:
            rental = await sw.get_rental_job(raw)
        except Exception as exc:  # noqa: BLE001
            raise HTTPException(
                status.HTTP_502_BAD_GATEWAY, f"Could not load stockwire-rental job {raw}"
            ) from exc
        job = ProductionJob(
            title=str(rental.get("description") or rental.get("job_code") or f"Job {raw}"),
            venue_name=str(rental.get("venue_name") or ""),
            notes="",
            stockwire_job_id=raw,
        )
        db.add(job)
        await db.commit()
        await db.refresh(job)
    return RedirectResponse(url=f"{web}/jobs/{job.id}")


@router.get("/jobs/{job_id}/deeplink")
async def outbound_deeplink(job_id: str, db=Depends(get_db)) -> dict:
    """Signed URL that opens this job in stockwire-rental (needs stockwire_job_id)."""
    cfg = await load_integration_config(db)
    secret = cfg.get("deeplink_secret")
    if not secret:
        raise HTTPException(
            status.HTTP_400_BAD_REQUEST, "Connect stockwire-rental first (deeplinks are not set up)"
        )
    result = await db.execute(select(ProductionJob).where(ProductionJob.id == job_id))
    job = result.scalars().first()
    if job is None or not job.stockwire_job_id:
        raise HTTPException(
            status.HTTP_400_BAD_REQUEST, "This job is not linked to a stockwire job"
        )
    token = sign_deeplink(
        secret,
        src="stagewire",
        job_id=job.stockwire_job_id,
        instance_id=STAGEWIRE_RENTAL_INSTANCE_ID,
        ttl_seconds=60 * 60 * 24 * 7,
    )
    url = f"{cfg['base_url'].rstrip('/')}/api/v1/settings/integrations/stagewire/open?token={token}"
    return {"url": url}


class LinkJobBody(BaseModel):
    stockwire_job_id: str | None = None


@router.get("/rental-jobs")
async def search_rental_jobs(search: str | None = None, db=Depends(get_db)) -> dict:
    """Search existing stockwire-rental jobs to link a Stagewire job to."""
    try:
        sw = await _stockwire_client(db)
        return await sw.search_rental_jobs(search)
    except Exception as exc:  # noqa: BLE001
        detail = f"Stockwire upstream error: {type(exc).__name__}: {exc}"
        raise HTTPException(status.HTTP_502_BAD_GATEWAY, detail) from exc


@router.post("/jobs/{job_id}/link")
async def link_job(job_id: str, payload: LinkJobBody | None = None, db=Depends(get_db)) -> dict:
    """Link this Stagewire job to an existing stockwire-rental job, or create one.

    With ``stockwire_job_id`` in the body the existing rental job is linked after it is
    verified; without it a new rental job is created.
    """
    cfg = await load_integration_config(db)
    if not cfg.get("api_key"):
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Stockwire integration is not configured")
    result = await db.execute(select(ProductionJob).where(ProductionJob.id == job_id))
    job = result.scalars().first()
    if job is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Production job not found")
    wanted = (payload.stockwire_job_id or "").strip() if payload else ""
    if job.stockwire_job_id:
        if wanted and wanted != job.stockwire_job_id:
            raise HTTPException(
                status.HTTP_409_CONFLICT,
                "This job is already linked to a different Stockwire job. Unlink it first.",
            )
        return {"stockwire_job_id": job.stockwire_job_id, "created": False}
    sw = client.StockwireClient(base_url=cfg["base_url"], token=cfg["api_key"])
    if wanted:
        try:
            existing_rental = await sw.get_rental_job(wanted)
        except Exception as exc:  # noqa: BLE001
            raise HTTPException(
                status.HTTP_404_NOT_FOUND, f"Stockwire job {wanted} was not found"
            ) from exc
        job.stockwire_job_id = str(existing_rental.get("id"))
        await db.commit()
        return {"stockwire_job_id": job.stockwire_job_id, "created": False}
    try:
        created = await sw.create_job(client.rental_job_payload(job))
    except Exception as exc:  # noqa: BLE001
        detail = f"Stockwire upstream error: {type(exc).__name__}: {exc}"
        raise HTTPException(status.HTTP_502_BAD_GATEWAY, detail) from exc
    job.stockwire_job_id = str(created.get("id"))
    await db.commit()
    return {"stockwire_job_id": job.stockwire_job_id, "created": True}
