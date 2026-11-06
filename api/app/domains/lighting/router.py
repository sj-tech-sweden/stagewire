from types import SimpleNamespace
from uuid import UUID

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.core.db import get_db
from app.domains.audio import service as audio_service
from app.domains.auth.deps import get_current_user
from app.domains.graph.mirror import MirrorToGraphRoute
from app.domains.lighting import importers, schemas, service
from app.domains.lighting.models import FixtureType
from app.domains.rigging import service as rigging_service

router = APIRouter(
    tags=["lighting"], dependencies=[Depends(get_current_user)], route_class=MirrorToGraphRoute
)

IMPORT_FORMATS = {".csv": importers.parse_csv, ".mvr": importers.parse_mvr}


async def _job_or_404(db: AsyncSession, job_id: UUID) -> None:
    if await audio_service.get_job(db, job_id) is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Production job not found")


async def _fixture_or_404(db: AsyncSession, job_id: UUID, fixture_id: UUID) -> SimpleNamespace:
    await _job_or_404(db, job_id)
    fixture = await service.get_fixture(db, job_id, fixture_id)
    if fixture is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Fixture not found")
    return fixture


async def _check_links(db: AsyncSession, job_id: UUID, data: dict) -> None:
    if data.get("rigging_point_id") is not None:
        if await rigging_service.get_point(db, job_id, data["rigging_point_id"]) is None:
            raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, "Rigging point not found")
    if data.get("power_node_id") is not None:
        if await rigging_service.get_node(db, job_id, data["power_node_id"]) is None:
            raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, "Power node not found")


async def _type_or_404(
    db: AsyncSession, type_id: UUID, job_id: UUID | None = None, venue_id: UUID | None = None
) -> FixtureType:
    if job_id is not None:
        await _job_or_404(db, job_id)
    else:
        await _venue_or_404(db, venue_id)
    fixture_type = await service.get_type(db, job_id=job_id, type_id=type_id, venue_id=venue_id)
    if fixture_type is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Fixture type not found")
    return fixture_type


async def _venue_or_404(db: AsyncSession, venue_id: UUID | None) -> None:
    from app.domains.venues import service as venue_service

    if venue_id is None or await venue_service.get_venue(db, venue_id) is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Venue not found")


async def _reads(db: AsyncSession, job_id: UUID, fixtures: list) -> list[schemas.FixtureRead]:
    names = {str(d.id): d.name for d in await audio_service.list_devices(db, job_id)}
    flags = service.dmx_flags(fixtures)
    reads = []
    for fixture in fixtures:
        read = schemas.FixtureRead.model_validate(fixture)
        read.device_name = names.get(str(fixture.device_id)) if fixture.device_id else None
        read.dmx_conflict, read.dmx_overflow = flags[fixture.id]
        reads.append(read)
    return reads


async def _read(db: AsyncSession, job_id: UUID, fixture) -> schemas.FixtureRead:
    reads = await _reads(db, job_id, await service.list_fixtures(db, job_id))
    return next(read for read in reads if read.id == fixture.id)


@router.get("/jobs/{job_id}/fixtures", response_model=list[schemas.FixtureRead])
async def list_fixtures(
    job_id: UUID, db: AsyncSession = Depends(get_db)
) -> list[schemas.FixtureRead]:
    await _job_or_404(db, job_id)
    return await _reads(db, job_id, await service.list_fixtures(db, job_id))


@router.post(
    "/jobs/{job_id}/fixtures",
    response_model=schemas.FixtureRead,
    status_code=status.HTTP_201_CREATED,
)
async def create_fixture(
    job_id: UUID,
    payload: schemas.FixtureCreate,
    db: AsyncSession = Depends(get_db),
) -> schemas.FixtureRead:
    await _job_or_404(db, job_id)
    data = payload.model_dump(exclude_unset=True)
    await _check_links(db, job_id, data)
    fixture = await service.create_fixture(db, job_id, data)
    return await _read(db, job_id, fixture)


@router.patch("/jobs/{job_id}/fixtures/{fixture_id}", response_model=schemas.FixtureRead)
async def update_fixture(
    job_id: UUID,
    fixture_id: UUID,
    payload: schemas.FixtureUpdate,
    db: AsyncSession = Depends(get_db),
) -> schemas.FixtureRead:
    fixture = await _fixture_or_404(db, job_id, fixture_id)
    data = payload.model_dump(exclude_unset=True)
    await _check_links(db, job_id, data)
    fixture = await service.update_fixture(db, job_id, fixture, data)
    return await _read(db, job_id, fixture)


@router.delete("/jobs/{job_id}/fixtures/{fixture_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_fixture(
    job_id: UUID, fixture_id: UUID, db: AsyncSession = Depends(get_db)
) -> None:
    fixture = await _fixture_or_404(db, job_id, fixture_id)
    await service.delete_fixture(db, fixture)


@router.post("/jobs/{job_id}/fixtures/import", response_model=schemas.FixtureImportResult)
async def import_fixtures(
    job_id: UUID,
    file: UploadFile = File(...),
    clear_imported: bool = True,
    db: AsyncSession = Depends(get_db),
) -> schemas.FixtureImportResult:
    await _job_or_404(db, job_id)
    name = (file.filename or "").lower()
    ext = next((e for e in IMPORT_FORMATS if name.endswith(e)), None)
    if ext is None:
        raise HTTPException(status.HTTP_415_UNSUPPORTED_MEDIA_TYPE, "Import a .csv or .mvr file")
    data = await file.read()
    if len(data) > get_settings().max_upload_bytes:
        raise HTTPException(status.HTTP_413_REQUEST_ENTITY_TOO_LARGE, "The file is too large")
    try:
        rows, errors = IMPORT_FORMATS[ext](data)
    except ValueError as exc:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, str(exc)) from exc
    created, devices_created, cleared = await service.import_rows(db, job_id, rows, clear_imported)
    return schemas.FixtureImportResult(
        created=created, devices_created=devices_created, cleared=cleared, errors=errors
    )


@router.get("/jobs/{job_id}/fixture-types", response_model=list[schemas.FixtureTypeRead])
async def list_types(job_id: UUID, db: AsyncSession = Depends(get_db)):
    await _job_or_404(db, job_id)
    return await service.list_types(db, job_id)


@router.post(
    "/jobs/{job_id}/fixture-types",
    response_model=schemas.FixtureTypeRead,
    status_code=status.HTTP_201_CREATED,
)
async def create_type(
    job_id: UUID, payload: schemas.FixtureTypeCreate, db: AsyncSession = Depends(get_db)
):
    await _job_or_404(db, job_id)
    return await service.create_type(db, job_id, payload.model_dump())


@router.post(
    "/jobs/{job_id}/fixture-types/from-stockwire",
    response_model=schemas.FixtureTypeRead,
    status_code=status.HTTP_201_CREATED,
)
async def import_type_from_stockwire(
    job_id: UUID, payload: schemas.StockwireTypeImport, db: AsyncSession = Depends(get_db)
):
    from app.domains.audio.router import stockwire_product_fetcher
    from app.domains.lighting.stockwire import type_from_product

    await _job_or_404(db, job_id)
    fetch = await stockwire_product_fetcher(db)
    if fetch is None:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, "Stockwire is not connected")
    try:
        product = await fetch(payload.product_id)
    except Exception as exc:
        raise HTTPException(status.HTTP_502_BAD_GATEWAY, "Stockwire could not be reached") from exc
    if not product:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Product not found in Stockwire")
    values = type_from_product(product)
    if not values["name"]:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, "The product has no name")
    return await service.import_stockwire_type(db, job_id, payload.product_id, values)


@router.patch("/jobs/{job_id}/fixture-types/{type_id}", response_model=schemas.FixtureTypeRead)
async def update_type(
    job_id: UUID,
    type_id: UUID,
    payload: schemas.FixtureTypeUpdate,
    db: AsyncSession = Depends(get_db),
):
    fixture_type = await _type_or_404(db, type_id, job_id=job_id)
    return await service.update_type(db, fixture_type, payload.model_dump(exclude_unset=True))


@router.delete("/jobs/{job_id}/fixture-types/{type_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_type(job_id: UUID, type_id: UUID, db: AsyncSession = Depends(get_db)) -> None:
    fixture_type = await _type_or_404(db, type_id, job_id=job_id)
    await service.delete_type(db, fixture_type)


@router.post(
    "/jobs/{job_id}/fixture-types/{type_id}/modes",
    response_model=schemas.FixtureModeRead,
    status_code=status.HTTP_201_CREATED,
)
async def create_mode(
    job_id: UUID,
    type_id: UUID,
    payload: schemas.FixtureModeCreate,
    db: AsyncSession = Depends(get_db),
):
    fixture_type = await _type_or_404(db, type_id, job_id=job_id)
    return await service.create_mode(db, fixture_type, payload.model_dump())


@router.patch(
    "/jobs/{job_id}/fixture-types/{type_id}/modes/{mode_id}",
    response_model=schemas.FixtureModeRead,
)
async def update_mode(
    job_id: UUID,
    type_id: UUID,
    mode_id: UUID,
    payload: schemas.FixtureModeUpdate,
    db: AsyncSession = Depends(get_db),
):
    await _type_or_404(db, type_id, job_id=job_id)
    mode = next(
        (m for m in (await service.get_type(db, job_id, type_id)).modes if m.id == mode_id), None
    )
    if mode is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Mode not found")
    return await service.update_mode(db, mode, payload.model_dump(exclude_unset=True))


@router.delete(
    "/jobs/{job_id}/fixture-types/{type_id}/modes/{mode_id}",
    status_code=status.HTTP_204_NO_CONTENT,
)
async def delete_mode(
    job_id: UUID, type_id: UUID, mode_id: UUID, db: AsyncSession = Depends(get_db)
) -> None:
    fixture_type = await _type_or_404(db, type_id, job_id=job_id)
    mode = next((m for m in fixture_type.modes if m.id == mode_id), None)
    if mode is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Mode not found")
    await service.delete_mode(db, mode)


# --- Venue-scoped fixture library -------------------------------------------------------------
# A venue's Standard Base Rig reuses the same fixture-type library machinery as a job; these routes
# are the venue counterpart of the /jobs/{job_id}/fixture-types* routes above, scoped to venue_id
# instead of job_id (the FixtureType/FixtureMode rows already carry a venue_id column).


@router.get("/venues/{venue_id}/fixture-types", response_model=list[schemas.FixtureTypeRead])
async def list_venue_types(venue_id: UUID, db: AsyncSession = Depends(get_db)):
    await _venue_or_404(db, venue_id)
    return await service.list_types(db, venue_id=venue_id)


@router.post(
    "/venues/{venue_id}/fixture-types",
    response_model=schemas.FixtureTypeRead,
    status_code=status.HTTP_201_CREATED,
)
async def create_venue_type(
    venue_id: UUID, payload: schemas.FixtureTypeCreate, db: AsyncSession = Depends(get_db)
):
    await _venue_or_404(db, venue_id)
    return await service.create_type(db, venue_id=venue_id, data=payload.model_dump())


@router.post(
    "/venues/{venue_id}/fixture-types/from-stockwire",
    response_model=schemas.FixtureTypeRead,
    status_code=status.HTTP_201_CREATED,
)
async def import_venue_type_from_stockwire(
    venue_id: UUID, payload: schemas.StockwireTypeImport, db: AsyncSession = Depends(get_db)
):
    from app.domains.audio.router import stockwire_product_fetcher
    from app.domains.lighting.stockwire import type_from_product

    await _venue_or_404(db, venue_id)
    fetch = await stockwire_product_fetcher(db)
    if fetch is None:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, "Stockwire is not connected")
    try:
        product = await fetch(payload.product_id)
    except Exception as exc:
        raise HTTPException(status.HTTP_502_BAD_GATEWAY, "Stockwire could not be reached") from exc
    if not product:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Product not found in Stockwire")
    values = type_from_product(product)
    if not values["name"]:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, "The product has no name")
    return await service.import_stockwire_type(
        db, venue_id=venue_id, product_id=payload.product_id, values=values
    )


@router.patch("/venues/{venue_id}/fixture-types/{type_id}", response_model=schemas.FixtureTypeRead)
async def update_venue_type(
    venue_id: UUID,
    type_id: UUID,
    payload: schemas.FixtureTypeUpdate,
    db: AsyncSession = Depends(get_db),
):
    fixture_type = await _type_or_404(db, type_id, venue_id=venue_id)
    return await service.update_type(db, fixture_type, payload.model_dump(exclude_unset=True))


@router.delete("/venues/{venue_id}/fixture-types/{type_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_venue_type(
    venue_id: UUID, type_id: UUID, db: AsyncSession = Depends(get_db)
) -> None:
    fixture_type = await _type_or_404(db, type_id, venue_id=venue_id)
    await service.delete_type(db, fixture_type)


@router.post(
    "/venues/{venue_id}/fixture-types/{type_id}/modes",
    response_model=schemas.FixtureModeRead,
    status_code=status.HTTP_201_CREATED,
)
async def create_venue_mode(
    venue_id: UUID,
    type_id: UUID,
    payload: schemas.FixtureModeCreate,
    db: AsyncSession = Depends(get_db),
):
    fixture_type = await _type_or_404(db, type_id, venue_id=venue_id)
    return await service.create_mode(db, fixture_type, payload.model_dump())


@router.patch(
    "/venues/{venue_id}/fixture-types/{type_id}/modes/{mode_id}",
    response_model=schemas.FixtureModeRead,
)
async def update_venue_mode(
    venue_id: UUID,
    type_id: UUID,
    mode_id: UUID,
    payload: schemas.FixtureModeUpdate,
    db: AsyncSession = Depends(get_db),
):
    await _type_or_404(db, type_id, venue_id=venue_id)
    type_row = await service.get_type(db, venue_id=venue_id, type_id=type_id)
    mode = next((m for m in type_row.modes if m.id == mode_id), None) if type_row else None
    if mode is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Mode not found")
    return await service.update_mode(db, mode, payload.model_dump(exclude_unset=True))


@router.delete(
    "/venues/{venue_id}/fixture-types/{type_id}/modes/{mode_id}",
    status_code=status.HTTP_204_NO_CONTENT,
)
async def delete_venue_mode(
    venue_id: UUID, type_id: UUID, mode_id: UUID, db: AsyncSession = Depends(get_db)
) -> None:
    fixture_type = await _type_or_404(db, type_id, venue_id=venue_id)
    mode = next((m for m in fixture_type.modes if m.id == mode_id), None)
    if mode is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Mode not found")
    await service.delete_mode(db, mode)


async def _check_device(db: AsyncSession, job_id: UUID, device_id: UUID | None) -> None:
    if device_id is None:
        return
    device = await audio_service.get_device(db, device_id)
    if device is None or device.job_id != job_id:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, "Device not found for this job")
