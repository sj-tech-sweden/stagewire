from uuid import UUID

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.core.db import get_db
from app.domains.audio import service as audio_service
from app.domains.auth.deps import get_current_user
from app.domains.lighting import importers, schemas, service
from app.domains.lighting.models import LightingFixture

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
    fixture = await service.create_fixture(db, job_id, payload.model_dump(exclude_unset=True))
    return await _read(db, job_id, fixture)


@router.patch("/jobs/{job_id}/fixtures/{fixture_id}", response_model=schemas.FixtureRead)
async def update_fixture(
    job_id: UUID,
    fixture_id: UUID,
    payload: schemas.FixtureUpdate,
    db: AsyncSession = Depends(get_db),
) -> schemas.FixtureRead:
    fixture = await _fixture_or_404(db, job_id, fixture_id)
    fixture = await service.update_fixture(
        db, job_id, fixture, payload.model_dump(exclude_unset=True)
    )
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
