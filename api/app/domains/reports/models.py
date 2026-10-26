from datetime import datetime
from uuid import UUID, uuid4

from sqlalchemy import JSON, Boolean, DateTime, Float, ForeignKey, Integer, String, Text, Uuid
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.db import Base


class ReportTemplate(Base):
    __tablename__ = "report_templates"

    id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid4)
    domain: Mapped[str] = mapped_column(String(64), index=True)
    report_type: Mapped[str] = mapped_column(String(64), index=True)
    locale: Mapped[str] = mapped_column(String(8), default="en")
    name: Mapped[str] = mapped_column(String(160))
    description: Mapped[str] = mapped_column(String(500), default="")
    body_html: Mapped[str] = mapped_column(Text)
    layout_json: Mapped[list[dict] | None] = mapped_column(JSON, nullable=True)
    page_count: Mapped[int] = mapped_column(Integer, default=1)
    stage_plot_options: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    is_default: Mapped[bool] = mapped_column(Boolean, default=False)
    is_builtin: Mapped[bool] = mapped_column(Boolean, default=False)
    letterhead_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("report_letterheads.id", ondelete="SET NULL"), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(),
        onupdate=lambda: datetime.now(),
    )

    letterhead: Mapped["ReportLetterhead | None"] = relationship(back_populates="templates")


class ReportLetterhead(Base):
    __tablename__ = "report_letterheads"

    id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid4)
    name: Mapped[str] = mapped_column(String(160), unique=True)
    file_name: Mapped[str] = mapped_column(String(255), unique=True)
    page_width_pt: Mapped[float] = mapped_column(Float)
    page_height_pt: Mapped[float] = mapped_column(Float)
    margin_top_mm: Mapped[float] = mapped_column(Float, default=20)
    margin_bottom_mm: Mapped[float] = mapped_column(Float, default=20)
    margin_left_mm: Mapped[float] = mapped_column(Float, default=20)
    margin_right_mm: Mapped[float] = mapped_column(Float, default=20)
    is_default: Mapped[bool] = mapped_column(Boolean, default=False, index=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now()
    )

    templates: Mapped[list[ReportTemplate]] = relationship(back_populates="letterhead")
