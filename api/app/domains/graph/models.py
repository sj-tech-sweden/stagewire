import uuid
from datetime import datetime

from sqlalchemy import (
    JSON,
    Boolean,
    DateTime,
    Float,
    ForeignKey,
    Integer,
    String,
    Text,
    Uuid,
    false,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.core.db import Base

JsonType = JSON().with_variant(JSONB(), "postgresql")


class GraphDevice(Base):
    __tablename__ = "graph_devices"

    id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4)
    job_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("production_jobs.id", ondelete="CASCADE"), nullable=True, index=True
    )
    # A base-rig device belongs to a venue (job_id NULL) until cloned onto a job.
    venue_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("venues.id", ondelete="CASCADE"), nullable=True, index=True
    )
    domain: Mapped[str] = mapped_column(String(32), nullable=False, index=True)
    kind: Mapped[str] = mapped_column(String(64), default="", nullable=False)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    notes: Mapped[str] = mapped_column(Text, default="", nullable=False)
    position: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    attributes: Mapped[dict] = mapped_column(JsonType, default=dict, nullable=False)
    ports: Mapped[list] = mapped_column(JsonType, default=list, nullable=False)
    canvas_x_cm: Mapped[float | None] = mapped_column(Float, nullable=True)
    canvas_y_cm: Mapped[float | None] = mapped_column(Float, nullable=True)
    canvas_rotation: Mapped[float] = mapped_column(Float, default=0.0, nullable=False)
    case_parent_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("graph_devices.id", ondelete="SET NULL"), nullable=True, index=True
    )
    stockwire_product_id: Mapped[str | None] = mapped_column(String(64), nullable=True, index=True)
    stockwire_product_name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    stockwire_device_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    stockwire_booked: Mapped[bool | None] = mapped_column(Boolean, nullable=True)
    stockwire_request_status: Mapped[str | None] = mapped_column(String(32), nullable=True)
    legacy_ref: Mapped[str | None] = mapped_column(String(128), nullable=True, index=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now()
    )
    revision: Mapped[int] = mapped_column(Integer, nullable=False, default=1, server_default="1")

    __mapper_args__ = {"version_id_col": revision}


class ConnectionEdge(Base):
    __tablename__ = "graph_connection_edges"

    id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4)
    job_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("production_jobs.id", ondelete="CASCADE"), nullable=True, index=True
    )
    # A base-rig edge belongs to a venue (job_id NULL) until cloned onto a job.
    venue_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("venues.id", ondelete="CASCADE"), nullable=True, index=True
    )
    signal: Mapped[str] = mapped_column(String(16), nullable=False, index=True)
    src_device_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("graph_devices.id", ondelete="CASCADE"), nullable=False, index=True
    )
    src_port: Mapped[str] = mapped_column(String(64), nullable=False)
    dst_device_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("graph_devices.id", ondelete="CASCADE"), nullable=False, index=True
    )
    dst_port: Mapped[str] = mapped_column(String(64), nullable=False)
    channels: Mapped[int] = mapped_column(Integer, default=1, nullable=False)
    phase: Mapped[str | None] = mapped_column(String(2), nullable=True)
    cable_label: Mapped[str] = mapped_column(String(128), default="", nullable=False)
    notes: Mapped[str] = mapped_column(Text, default="", nullable=False)
    attributes: Mapped[dict] = mapped_column(JsonType, default=dict, nullable=False)
    graph_edited: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False, server_default=false()
    )
    revision: Mapped[int] = mapped_column(Integer, nullable=False, default=1, server_default="1")

    __mapper_args__ = {"version_id_col": revision}


def scope_filter(model, job_id: uuid.UUID | None = None, venue_id: uuid.UUID | None = None):
    """Narrow a graph row (device or edge) to exactly one context: a job or a venue.

    Mirrors the lighting ``_scope`` helper. A row can never belong to both scopes at once
    (the venue base rig sets ``venue_id`` and leaves ``job_id`` NULL), so passing both, or
    neither, is a programming error. Existing callers that pass only ``job_id`` keep working.
    """
    if job_id is not None and venue_id is not None:
        raise ValueError("a graph row cannot be scoped to both a job and a venue")
    if job_id is not None:
        return model.job_id == job_id
    if venue_id is not None:
        return model.venue_id == venue_id
    raise ValueError("a graph row requires a job_id or venue_id")
