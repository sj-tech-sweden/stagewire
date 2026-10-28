import re
import secrets
from pathlib import Path
from uuid import UUID

from fastapi import APIRouter, Depends, File, Form, HTTPException, Query, UploadFile, status
from fastapi.responses import Response
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.core.db import get_db
from app.domains.auth.deps import get_current_user, require_admin
from app.domains.reports import schemas
from app.domains.reports.models import ReportLetterhead, ReportTemplate
from app.domains.reports.registry import (
    REPORT_DEFINITIONS,
    REPORT_DEFINITIONS_BY_KEY,
    ensure_default_templates,
)
from app.domains.reports.render import (
    ReportRenderError,
    read_letterhead_pdf,
    render_letterhead_preview,
    render_report_pdf,
)

router = APIRouter(prefix="/reports", tags=["reports"])
admin_router = APIRouter(tags=["reports"], dependencies=[Depends(require_admin)])


async def _get_default_template(
    db: AsyncSession, domain: str, report_type: str, locale: str = "en"
) -> ReportTemplate | None:
    result = await db.execute(
        select(ReportTemplate)
        .where(
            ReportTemplate.domain == domain,
            ReportTemplate.report_type == report_type,
            ReportTemplate.locale == locale,
            ReportTemplate.is_default.is_(True),
        )
        .order_by(ReportTemplate.created_at)
    )
    return result.scalars().first()


async def _set_default_template(db: AsyncSession, template: ReportTemplate) -> None:
    result = await db.execute(
        select(ReportTemplate).where(
            ReportTemplate.domain == template.domain,
            ReportTemplate.report_type == template.report_type,
            ReportTemplate.locale == template.locale,
        )
    )
    for existing in result.scalars().all():
        existing.is_default = existing.id == template.id


async def _set_default_letterhead(db: AsyncSession, letterhead: ReportLetterhead) -> None:
    result = await db.execute(select(ReportLetterhead))
    for existing in result.scalars().all():
        existing.is_default = existing.id == letterhead.id


def _get_registered_type(domain: str, report_type: str):
    definition = REPORT_DEFINITIONS_BY_KEY.get(f"{domain}.{report_type}")
    if definition is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Report type not found")
    return definition


def _validate_page_margins(
    page_width_pt: float,
    page_height_pt: float,
    top_mm: float,
    bottom_mm: float,
    left_mm: float,
    right_mm: float,
) -> None:
    width_mm = page_width_pt * 25.4 / 72
    height_mm = page_height_pt * 25.4 / 72
    if left_mm + right_mm >= width_mm or top_mm + bottom_mm >= height_mm:
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_CONTENT,
            "Letterhead margins must leave a printable area on the PDF page",
        )


def _normalize_name(name: str) -> str:
    normalized = name.strip()
    if not normalized:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, "Name cannot be empty")
    return normalized


@router.get("/types", response_model=list[schemas.ReportTypeRead])
async def list_report_types(
    locale: str = Query(default="en", pattern="^(en|sv)$"),
    _user=Depends(get_current_user),
) -> list[schemas.ReportTypeRead]:
    return [definition.read(locale) for definition in REPORT_DEFINITIONS]


@router.get("/templates", response_model=list[schemas.ReportTemplateRead])
async def list_templates(
    domain: str | None = None,
    report_type: str | None = None,
    db: AsyncSession = Depends(get_db),
    _user=Depends(get_current_user),
) -> list[schemas.ReportTemplateRead]:
    await ensure_default_templates(db)
    query = select(ReportTemplate).order_by(
        ReportTemplate.domain,
        ReportTemplate.report_type,
        ReportTemplate.locale,
        ReportTemplate.created_at,
    )
    if domain:
        query = query.where(ReportTemplate.domain == domain)
    if report_type:
        query = query.where(ReportTemplate.report_type == report_type)
    result = await db.execute(query)
    return [schemas.ReportTemplateRead.model_validate(item) for item in result.scalars().all()]


@admin_router.post("/templates", response_model=schemas.ReportTemplateRead, status_code=201)
async def create_template(
    payload: schemas.ReportTemplateCreate,
    db: AsyncSession = Depends(get_db),
) -> schemas.ReportTemplateRead:
    await ensure_default_templates(db)
    definition = _get_registered_type(payload.domain, payload.report_type)
    template = ReportTemplate(
        domain=definition.domain,
        report_type=definition.report_type,
        locale=payload.locale,
        name=_normalize_name(payload.name),
        description=definition.description,
        body_html=payload.body_html,
        layout_json=payload.layout_json,
        page_count=payload.page_count,
        stage_plot_options=(
            payload.stage_plot_options.model_dump() if payload.stage_plot_options else None
        ),
        letterhead_id=payload.letterhead_id,
        is_default=False,
        is_builtin=False,
    )
    if template.letterhead_id and await db.get(ReportLetterhead, template.letterhead_id) is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Letterhead not found")
    db.add(template)
    await db.commit()
    await db.refresh(template)
    return schemas.ReportTemplateRead.model_validate(template)


@admin_router.put("/templates/{template_id}", response_model=schemas.ReportTemplateRead)
async def update_template(
    template_id: UUID,
    payload: schemas.ReportTemplateUpdate,
    db: AsyncSession = Depends(get_db),
) -> schemas.ReportTemplateRead:
    template = await db.get(ReportTemplate, template_id)
    if template is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Report template not found")
    if payload.letterhead_id and await db.get(ReportLetterhead, payload.letterhead_id) is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Letterhead not found")
    template.name = _normalize_name(payload.name)
    template.body_html = payload.body_html
    if "layout_json" in payload.model_fields_set:
        template.layout_json = payload.layout_json
    template.page_count = payload.page_count
    if "stage_plot_options" in payload.model_fields_set:
        template.stage_plot_options = (
            payload.stage_plot_options.model_dump() if payload.stage_plot_options else None
        )
    template.letterhead_id = payload.letterhead_id
    if payload.is_default:
        await _set_default_template(db, template)
    await db.commit()
    await db.refresh(template)
    return schemas.ReportTemplateRead.model_validate(template)


@admin_router.delete("/templates/{template_id}", status_code=204)
async def delete_template(template_id: UUID, db: AsyncSession = Depends(get_db)) -> None:
    template = await db.get(ReportTemplate, template_id)
    if template is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Report template not found")
    if template.is_default:
        raise HTTPException(
            status.HTTP_409_CONFLICT,
            "Choose another default template before deleting this template",
        )
    await db.delete(template)
    await db.commit()


@router.get("/letterheads", response_model=list[schemas.ReportLetterheadRead])
async def list_letterheads(
    db: AsyncSession = Depends(get_db), _user=Depends(get_current_user)
) -> list[schemas.ReportLetterheadRead]:
    result = await db.execute(
        select(ReportLetterhead).order_by(ReportLetterhead.is_default.desc(), ReportLetterhead.name)
    )
    return [schemas.ReportLetterheadRead.model_validate(item) for item in result.scalars().all()]


@admin_router.post(
    "/letterheads/upload", response_model=schemas.ReportLetterheadRead, status_code=201
)
async def upload_letterhead(
    file: UploadFile = File(...),
    name: str = Form(..., min_length=1, max_length=160),
    is_default: bool = Form(False),
    margin_top_mm: float = Form(20, ge=0, le=200),
    margin_bottom_mm: float = Form(20, ge=0, le=200),
    margin_left_mm: float = Form(20, ge=0, le=200),
    margin_right_mm: float = Form(20, ge=0, le=200),
    db: AsyncSession = Depends(get_db),
) -> schemas.ReportLetterheadRead:
    normalized_name = _normalize_name(name)
    max_upload_bytes = get_settings().max_upload_bytes
    content = await file.read(max_upload_bytes + 1)
    if len(content) > max_upload_bytes:
        raise HTTPException(
            status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
            f"Letterhead PDF exceeds {max_upload_bytes} bytes",
        )
    if not content.startswith(b"%PDF-"):
        raise HTTPException(
            status.HTTP_415_UNSUPPORTED_MEDIA_TYPE, "Only PDF letterheads are accepted"
        )
    try:
        page_width, page_height, _ = read_letterhead_pdf(content)
    except ReportRenderError as exc:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, str(exc)) from exc
    _validate_page_margins(
        page_width,
        page_height,
        margin_top_mm,
        margin_bottom_mm,
        margin_left_mm,
        margin_right_mm,
    )

    folder = Path(get_settings().upload_dir) / "report-letterheads"
    folder.mkdir(parents=True, exist_ok=True)
    file_name = f"{secrets.token_hex(16)}.pdf"
    destination = folder / file_name
    destination.write_bytes(content)
    letterhead = ReportLetterhead(
        name=normalized_name,
        file_name=file_name,
        page_width_pt=page_width,
        page_height_pt=page_height,
        margin_top_mm=margin_top_mm,
        margin_bottom_mm=margin_bottom_mm,
        margin_left_mm=margin_left_mm,
        margin_right_mm=margin_right_mm,
        is_default=is_default,
    )
    if is_default:
        await _set_default_letterhead(db, letterhead)
    db.add(letterhead)
    try:
        await db.commit()
    except IntegrityError as exc:
        await db.rollback()
        destination.unlink(missing_ok=True)
        raise HTTPException(
            status.HTTP_409_CONFLICT, "A letterhead with that name already exists"
        ) from exc
    await db.refresh(letterhead)
    return schemas.ReportLetterheadRead.model_validate(letterhead)


@router.get("/letterheads/{letterhead_id}/preview")
async def get_letterhead_preview(
    letterhead_id: UUID,
    db: AsyncSession = Depends(get_db),
    _user=Depends(get_current_user),
) -> Response:
    letterhead = await db.get(ReportLetterhead, letterhead_id)
    if letterhead is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Letterhead not found")
    path = Path(get_settings().upload_dir) / "report-letterheads" / letterhead.file_name
    if not path.is_file():
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Letterhead PDF file not found")
    try:
        image = render_letterhead_preview(path.read_bytes())
    except ReportRenderError as exc:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, str(exc)) from exc
    return Response(content=image, media_type="image/png")


@admin_router.put("/letterheads/{letterhead_id}", response_model=schemas.ReportLetterheadRead)
async def update_letterhead(
    letterhead_id: UUID,
    payload: schemas.LetterheadUpdate,
    db: AsyncSession = Depends(get_db),
) -> schemas.ReportLetterheadRead:
    letterhead = await db.get(ReportLetterhead, letterhead_id)
    if letterhead is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Letterhead not found")
    changes = payload.model_dump(exclude_unset=True)
    if changes.get("name") is not None:
        letterhead.name = _normalize_name(changes["name"])
    for key in (
        "margin_top_mm",
        "margin_bottom_mm",
        "margin_left_mm",
        "margin_right_mm",
    ):
        if key in changes and changes[key] is not None:
            setattr(letterhead, key, changes[key])
    _validate_page_margins(
        letterhead.page_width_pt,
        letterhead.page_height_pt,
        letterhead.margin_top_mm,
        letterhead.margin_bottom_mm,
        letterhead.margin_left_mm,
        letterhead.margin_right_mm,
    )
    if changes.get("is_default"):
        await _set_default_letterhead(db, letterhead)
    try:
        await db.commit()
    except IntegrityError as exc:
        await db.rollback()
        raise HTTPException(
            status.HTTP_409_CONFLICT, "A letterhead with that name already exists"
        ) from exc
    await db.refresh(letterhead)
    return schemas.ReportLetterheadRead.model_validate(letterhead)


@admin_router.delete("/letterheads/{letterhead_id}", status_code=204)
async def delete_letterhead(letterhead_id: UUID, db: AsyncSession = Depends(get_db)) -> None:
    letterhead = await db.get(ReportLetterhead, letterhead_id)
    if letterhead is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Letterhead not found")
    folder = Path(get_settings().upload_dir) / "report-letterheads"
    for template in (
        await db.execute(
            select(ReportTemplate).where(ReportTemplate.letterhead_id == letterhead_id)
        )
    ).scalars():
        template.letterhead_id = None
    await db.delete(letterhead)
    await db.commit()
    (folder / letterhead.file_name).unlink(missing_ok=True)


@router.get("/jobs/{job_id}/{domain}/{report_type}/pdf")
async def generate_report(
    job_id: UUID,
    domain: str,
    report_type: str,
    template_id: UUID | None = Query(default=None),
    patchpoint_id: UUID | None = Query(default=None),
    stage_plot_view: str | None = Query(default=None, pattern="^(stage|venue)$"),
    show_coverage: bool | None = None,
    show_camera_coverage: bool | None = None,
    show_projector_coverage: bool | None = None,
    camera_view_mode: str | None = Query(default=None, pattern="^(range|chosen)$"),
    show_cables: bool | None = None,
    show_cableways: bool | None = None,
    locale: str = Query(default="en", pattern="^(en|sv)$"),
    db: AsyncSession = Depends(get_db),
    _user=Depends(get_current_user),
) -> Response:
    _get_registered_type(domain, report_type)
    await ensure_default_templates(db)
    template = (
        await db.get(ReportTemplate, template_id)
        if template_id
        else await _get_default_template(db, domain, report_type, locale)
    )
    if template is None or (template.domain, template.report_type) != (domain, report_type):
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Report template not found")
    try:
        stage_plot_options = {
            key: value
            for key, value in {
                "view": stage_plot_view,
                "show_coverage": show_coverage,
                "show_camera_coverage": show_camera_coverage,
                "show_projector_coverage": show_projector_coverage,
                "camera_view_mode": camera_view_mode,
                "show_cables": show_cables,
                "show_cableways": show_cableways,
            }.items()
            if value is not None
        }
        content = await render_report_pdf(
            db,
            template,
            job_id,
            patchpoint_id,
            stage_plot_options or None,
        )
    except LookupError as exc:
        raise HTTPException(status.HTTP_404_NOT_FOUND, str(exc)) from exc
    except ReportRenderError as exc:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, str(exc)) from exc
    safe_name = re.sub(r"[^a-zA-Z0-9_-]+", "-", template.name).strip("-").lower() or "report"
    return Response(
        content=content,
        media_type="application/pdf",
        headers={"Content-Disposition": f'attachment; filename="{safe_name}.pdf"'},
    )


@router.get("/jobs/{job_id}/{domain}/{report_type}/preview")
async def preview_report(
    job_id: UUID,
    domain: str,
    report_type: str,
    template_id: UUID | None = Query(default=None),
    patchpoint_id: UUID | None = Query(default=None),
    stage_plot_view: str | None = Query(default=None, pattern="^(stage|venue)$"),
    show_coverage: bool | None = None,
    show_camera_coverage: bool | None = None,
    show_projector_coverage: bool | None = None,
    camera_view_mode: str | None = Query(default=None, pattern="^(range|chosen)$"),
    show_cables: bool | None = None,
    show_cableways: bool | None = None,
    locale: str = Query(default="en", pattern="^(en|sv)$"),
    db: AsyncSession = Depends(get_db),
    _user=Depends(get_current_user),
) -> Response:
    response = await generate_report(
        job_id=job_id,
        domain=domain,
        report_type=report_type,
        template_id=template_id,
        patchpoint_id=patchpoint_id,
        stage_plot_view=stage_plot_view,
        show_coverage=show_coverage,
        show_camera_coverage=show_camera_coverage,
        show_projector_coverage=show_projector_coverage,
        camera_view_mode=camera_view_mode,
        show_cables=show_cables,
        show_cableways=show_cableways,
        locale=locale,
        db=db,
        _user=_user,
    )
    return Response(content=response.body, media_type="application/pdf")


router.include_router(admin_router)
