from datetime import datetime
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


class ReportField(BaseModel):
    key: str
    label: str
    kind: str = "text"


class ReportTable(BaseModel):
    key: str
    label: str
    columns: list[ReportField]


class ReportTypeRead(BaseModel):
    key: str
    domain: str
    report_type: str
    name: str
    description: str
    fields: list[ReportField]
    tables: list[ReportTable]
    has_stage_plot: bool = False
    requires_patchpoint: bool = False


class StagePlotOptions(BaseModel):
    model_config = ConfigDict(extra="forbid")

    view: Literal["stage", "venue"] = "stage"
    show_coverage: bool = False
    show_cables: bool = False
    show_cableways: bool = False


class ReportTemplateUpdate(BaseModel):
    name: str = Field(min_length=1, max_length=160)
    body_html: str = Field(min_length=1, max_length=100_000)
    layout_json: list[dict] | None = None
    page_count: int = Field(default=1, ge=1, le=100)
    stage_plot_options: StagePlotOptions | None = None
    letterhead_id: UUID | None = None
    is_default: bool | None = None


class ReportTemplateCreate(BaseModel):
    domain: str = Field(min_length=1, max_length=64)
    report_type: str = Field(min_length=1, max_length=64)
    locale: Literal["en", "sv"] = "en"
    name: str = Field(min_length=1, max_length=160)
    body_html: str = Field(min_length=1, max_length=100_000)
    layout_json: list[dict] | None = None
    page_count: int = Field(default=1, ge=1, le=100)
    stage_plot_options: StagePlotOptions | None = None
    letterhead_id: UUID | None = None


class ReportTemplateRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    domain: str
    report_type: str
    locale: str
    name: str
    description: str
    body_html: str
    layout_json: list[dict] | None
    page_count: int
    stage_plot_options: dict | None
    is_default: bool
    is_builtin: bool
    letterhead_id: UUID | None
    created_at: datetime
    updated_at: datetime


class ReportLetterheadRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    name: str
    page_width_pt: float
    page_height_pt: float
    margin_top_mm: float
    margin_bottom_mm: float
    margin_left_mm: float
    margin_right_mm: float
    is_default: bool
    created_at: datetime


class LetterheadUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=160)
    is_default: bool | None = None
    margin_top_mm: float | None = Field(default=None, ge=0, le=200)
    margin_bottom_mm: float | None = Field(default=None, ge=0, le=200)
    margin_left_mm: float | None = Field(default=None, ge=0, le=200)
    margin_right_mm: float | None = Field(default=None, ge=0, le=200)
