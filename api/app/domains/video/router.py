from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.db import get_db
from app.domains.audio import service as audio_service
from app.domains.auth.deps import get_current_user
from app.domains.graph.video_readers import load_video_lists
from app.domains.video import schemas, service

# Video lists are authored on the graph (/jobs/{id}/graph/video-*); these endpoints only read them,
# in the shapes the reports page and the exports already use.
router = APIRouter(tags=["video"], dependencies=[Depends(get_current_user)])


async def _job_or_404(db: AsyncSession, job_id: UUID) -> None:
    if await audio_service.get_job(db, job_id) is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Production job not found")


@router.get("/jobs/{job_id}/video-patch-sheets", response_model=list[schemas.VideoSheet])
async def list_video_patch_sheets(job_id: UUID, db: AsyncSession = Depends(get_db)) -> list[dict]:
    await _job_or_404(db, job_id)
    return await service.build_video_sheets(db, job_id, await load_video_lists(db, job_id))


@router.get("/jobs/{job_id}/video-lists", response_model=list[schemas.VideoInputListRead])
async def list_video_lists(
    job_id: UUID, db: AsyncSession = Depends(get_db)
) -> list[schemas.VideoInputListRead]:
    await _job_or_404(db, job_id)
    lists = await load_video_lists(db, job_id)
    return [schemas.VideoInputListRead.model_validate(lst) for lst in lists]
