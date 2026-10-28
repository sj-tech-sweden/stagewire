from uuid import UUID

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.core.db import get_db
from app.domains.audio import service as audio_service
from app.domains.auth.deps import get_current_user
from app.domains.lighting import importers, schemas, service
from app.domains.lighting.models import FixtureType, LightingFixture
from app.domains.rigging import service as rigging_service

router = APIRouter(tags=["lighting"], dependencies=[Depends(get_current_user)])

IMPORT_FORMATS = {".csv": importers.parse_csv, ".mvr": importers.parse_mvr}


async def _job_or_404(db: AsyncSession, job_id: UUID) -> None:
    if await audio_service.get_job(db, job_id) is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Production job not found")


async def _fixture_or_404(db: AsyncSession, job_id: UUID, fixture_id: UUID) -> LightingFixture:
    await _job_or_404(db, job_id)
    fixture = await service.get_fixture(db, job_id, fixture_id)
    if fixture is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Fixture not found")
    return fixture


async def _check_links(db: AsyncSession, job_id: UUID, data: dict) -> None:
    if data.get("rigging_point_id") is not None:
        if await rigging_service.get_point(db, job_id, data["rigging_point_id"]) is None:
            raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, "Rigging point not found")
    if data.get("power_circuit_id") is not None:
        if await rigging_service.get_circuit(db, job_id, data["power_circuit_id"]) is None:
            raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, "Circuit not found")


async def _type_or_404(db: AsyncSession, job_id: UUID, type_id: UUID) -> FixtureType:
    await _job_or_404(db, job_id)
    fixture_type = await service.get_type(db, job_id, type_id)
    if fixture_type is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Fixture type not found")
    return fixture_type


async def _reads(
    db: AsyncSession, job_id: UUID, fixtures: list[LightingFixture]
) -> list[schemas.FixtureRead]:
    names = {str(d.id): d.name for d in await audio_service.list_devices(db, job_id)}
    flags = service.dmx_flags(fixtures)
    reads = []
    for fixture in fixtures:
        read = schemas.FixtureRead.model_validate(fixture)
        read.device_name = names.get(str(fixture.device_id)) if fixture.device_id else None
        read.dmx_conflict, read.dmx_overflow = flags[fixture.id]
        reads.append(read)
    return reads


async def _read(db: AsyncSession, job_id: UUID, fixture: LightingFixture) -> schemas.FixtureRead:
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


@router.patch("/jobs/{job_id}/fixture-types/{type_id}", response_model=schemas.FixtureTypeRead)
async def update_type(
    job_id: UUID,
    type_id: UUID,
    payload: schemas.FixtureTypeUpdate,
    db: AsyncSession = Depends(get_db),
):
    fixture_type = await _type_or_404(db, job_id, type_id)
    return await service.update_type(db, fixture_type, payload.model_dump(exclude_unset=True))


@router.delete("/jobs/{job_id}/fixture-types/{type_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_type(job_id: UUID, type_id: UUID, db: AsyncSession = Depends(get_db)) -> None:
    fixture_type = await _type_or_404(db, job_id, type_id)
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
    fixture_type = await _type_or_404(db, job_id, type_id)
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
    await _type_or_404(db, job_id, type_id)
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
    fixture_type = await _type_or_404(db, job_id, type_id)
    mode = next((m for m in fixture_type.modes if m.id == mode_id), None)
    if mode is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Mode not found")
    await service.delete_mode(db, mode)
