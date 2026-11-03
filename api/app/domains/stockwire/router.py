import asyncio
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status
from fastapi.responses import RedirectResponse
from pydantic import BaseModel
from sqlalchemy import select

from app.core.config import get_settings
from app.core.db import get_db
from app.domains.audio.models import ProductionJob
from app.domains.auth.deps import get_current_user
from app.domains.graph.models import GraphDevice
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


async def _catalog_client(db):
    """Return a Stockwire client, or ``None`` when the integration is not configured.

    Catalog browsing (categories / product search) degrades gracefully to empty
    results so the UI works without the stockwire-rental integration set up.
    """
    cfg = await load_integration_config(db)
    if not cfg.get("api_key"):
        return None
    return client.StockwireClient(base_url=cfg["base_url"], token=cfg["api_key"])


@router.get("/jobs/{job_id}")
async def get_job(job_id: str, db=Depends(get_db)) -> dict:
    try:
        sw = await _stockwire_client(db)
        return await sw.get_job(job_id)
    except Exception as exc:  # noqa: BLE001 - surface upstream errors to caller
        detail = f"Stockwire upstream error: {type(exc).__name__}: {exc}"
        raise HTTPException(status.HTTP_502_BAD_GATEWAY, detail) from exc


def _availability(resp) -> tuple[int, int, int]:
    """Pull (available, total, reserved) out of a Stockwire availability response.

    The endpoint returns a single object whose ``available_quantity`` is already the minimum
    available across the requested date range. We fall back to ``total_quantity`` minus
    ``max_reserved_quantity`` when the explicit field is missing, and tolerate a bare integer
    or a per-day mapping as a last resort. Unrecognised shapes count as zero available.
    """
    if isinstance(resp, dict):
        if "available_quantity" in resp:
            available = int(resp["available_quantity"])
        elif "total_quantity" in resp and "max_reserved_quantity" in resp:
            available = int(resp["total_quantity"]) - int(resp["max_reserved_quantity"])
        else:
            nums = [v for v in resp.values() if isinstance(v, (int, float))]
            available = int(min(nums)) if nums else 0
        total = int(resp.get("total_quantity", 0) or 0)
        reserved = int(resp.get("max_reserved_quantity", 0) or 0)
        return available, total, reserved
    if isinstance(resp, (int, float)):
        return int(resp), int(resp), 0
    return 0, 0, 0


@router.get(
    "/jobs/{job_id}/availability",
    response_model=schemas.JobAvailabilityResponse,
)
async def job_availability(job_id: str, db=Depends(get_db)) -> dict:
    """Minimum available quantity per Stockwire product over the job's date range.

    Every device in the job that is linked to a Stockwire product is counted as "needed";
    for each product we ask Stockwire for the minimum available quantity across the job's
    start/end dates and flag ``short`` when the job needs more than is available. Degrades
    gracefully: ``configured`` is false when the integration is off, ``missing_dates`` when
    the job has no date range to query against.
    """
    try:
        job_uuid = UUID(job_id)
    except ValueError:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Production job not found") from None
    result = await db.execute(select(ProductionJob).where(ProductionJob.id == job_uuid))
    job = result.scalars().first()
    if job is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Production job not found")

    cfg = await load_integration_config(db)
    if not cfg.get("api_key"):
        return {"configured": False, "items": []}

    start = job.start_date.isoformat() if job.start_date else None
    end = job.end_date.isoformat() if job.end_date else None
    if not start or not end:
        return {
            "configured": True,
            "missing_dates": True,
            "start_date": start,
            "end_date": end,
            "items": [],
        }

    devices = (
        (
            await db.execute(
                select(GraphDevice).where(
                    GraphDevice.job_id == job.id,
                    GraphDevice.stockwire_product_id.is_not(None),
                )
            )
        )
        .scalars()
        .all()
    )

    needed: dict[str, int] = {}
    names: dict[str, str | None] = {}
    for d in devices:
        pid = str(d.stockwire_product_id)
        needed[pid] = needed.get(pid, 0) + 1
        names.setdefault(pid, d.stockwire_product_name)

    sw = client.StockwireClient(base_url=cfg["base_url"], token=cfg["api_key"])

    async def fetch(pid: str) -> schemas.JobProductAvailability:
        try:
            resp = await sw.get_availability(pid, start, end)
            available, total, reserved = _availability(resp)
        except Exception:  # noqa: BLE001 - treat upstream errors as "cannot confirm stock"
            available, total, reserved = 0, 0, 0
        return schemas.JobProductAvailability(
            product_id=pid,
            product_name=names.get(pid),
            needed=needed[pid],
            available=available,
            total=total,
            reserved=reserved,
            short=available < needed[pid],
        )

    product_ids = list(needed)
    if not product_ids:
        items = []
    else:
        try:
            # One batch call covers every product the job links to, replacing the per-product loop.
            # The upstream returns a flat list; map it back onto product ids before parsing.
            raw = await sw.get_availability_batch(product_ids, start, end)
            items = []
            for pid in product_ids:
                available, total, reserved = _availability(raw.get(pid, {}))
                items.append(
                    schemas.JobProductAvailability(
                        product_id=pid,
                        product_name=names.get(pid),
                        needed=needed[pid],
                        available=available,
                        total=total,
                        reserved=reserved,
                        short=available < needed[pid],
                    )
                )
        except Exception:  # noqa: BLE001 - degrade to the isolated per-product path
            items = await asyncio.gather(*(fetch(pid) for pid in product_ids))
    items.sort(key=lambda i: (i.product_name or "", i.product_id))
    return {
        "configured": True,
        "missing_dates": False,
        "start_date": start,
        "end_date": end,
        "items": items,
    }


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
    sw = await _catalog_client(db)
    if sw is None:
        return {"items": []}
    try:
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


@router.get("/own-products")
async def own_products(
    search: str | None = None,
    category_id: list[int] | None = Query(default=None),
    skip: int = 0,
    limit: int = 20,
    db=Depends(get_db),
) -> dict:
    """Own equipment: products that have devices, the device count being the quantity."""
    sw = await _catalog_client(db)
    if sw is None:
        return {"items": [], "total": 0}
    try:
        return await sw.search_own_products(
            q=search, category_ids=category_id, skip=skip, limit=limit
        )
    except Exception as exc:  # noqa: BLE001
        detail = f"Stockwire upstream error: {type(exc).__name__}: {exc}"
        raise HTTPException(status.HTTP_502_BAD_GATEWAY, detail) from exc


@router.get("/catalog/search")
async def search_catalog(
    q: str | None = None,
    category: list[str] | None = Query(default=None),
    manufacturer: list[str] | None = Query(default=None),
    attr: list[str] | None = Query(default=None, description="key:value spec filters"),
    job_id: str | None = Query(default=None, description="Stockwire rental job id"),
    start_date: str | None = Query(default=None, description="Inclusive rental start (YYYY-MM-DD)"),
    end_date: str | None = Query(default=None, description="Inclusive rental end (YYYY-MM-DD)"),
    exclude_rental: bool = Query(default=True, description="Hide rental-in products by default"),
    skip: int = 0,
    limit: int = 50,
    db=Depends(get_db),
) -> dict:
    sw = await _catalog_client(db)
    if sw is None:
        return {
            "items": [],
            "total": 0,
            "facets": {},
            "availability": {"date_range_supported": False},
        }
    attributes = dict(pair.split(":", 1) for pair in attr or [] if ":" in pair)
    try:
        return await sw.search_catalog(
            q=q,
            categories=category,
            manufacturers=manufacturer,
            attributes=attributes,
            job_id=job_id,
            start_date=start_date,
            end_date=end_date,
            exclude_rental=exclude_rental,
            skip=skip,
            limit=limit,
        )
    except Exception as exc:  # noqa: BLE001
        detail = f"Stockwire upstream error: {type(exc).__name__}: {exc}"
        raise HTTPException(status.HTTP_502_BAD_GATEWAY, detail) from exc


@router.get("/catalog/cases")
async def list_cases(db=Depends(get_db)) -> dict:
    sw = await _catalog_client(db)
    if sw is None:
        return {"items": []}
    try:
        return {"items": await sw.list_cases()}
    except Exception as exc:  # noqa: BLE001
        detail = f"Stockwire upstream error: {type(exc).__name__}: {exc}"
        raise HTTPException(status.HTTP_502_BAD_GATEWAY, detail) from exc


@router.get("/catalog/cases/{case_device_id}/children")
async def case_children(case_device_id: str, db=Depends(get_db)) -> dict:
    sw = await _catalog_client(db)
    if sw is None:
        return {"items": []}
    try:
        return {"items": await sw.list_child_devices(case_device_id)}
    except Exception as exc:  # noqa: BLE001
        detail = f"Stockwire upstream error: {type(exc).__name__}: {exc}"
        raise HTTPException(status.HTTP_502_BAD_GATEWAY, detail) from exc


@router.get("/products/{product_id}/device-specs")
async def get_device_specs(product_id: int | str, db=Depends(get_db)) -> dict:
    """What an import needs from a product: its connector groups, power inlet, I/O counts, weight
    and power, read with the tolerant rules in ``audio/device_specs.py``."""
    from app.domains.audio.device_specs import product_io_specs, product_physical_specs

    try:
        sw = await _stockwire_client(db)
        product = await sw.get_product(product_id)
    except Exception as exc:  # noqa: BLE001
        detail = f"Stockwire upstream error: {type(exc).__name__}: {exc}"
        raise HTTPException(status.HTTP_502_BAD_GATEWAY, detail) from exc
    return {
        "id": product.get("id"),
        "name": product.get("name"),
        **product_io_specs(product),
        **product_physical_specs(product),
    }


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
    sw = await _catalog_client(db)
    if sw is None:
        return {"categories": []}
    try:
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
