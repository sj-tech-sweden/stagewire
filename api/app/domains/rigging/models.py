import uuid

from sqlalchemy import JSON, Boolean, Float, ForeignKey, Integer, String, Text, Uuid
from sqlalchemy.orm import Mapped, mapped_column

from app.core.db import Base


class RiggingPoint(Base):
    """A truss or hanging point with a weight capacity."""

    __tablename__ = "rigging_points"

    id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4)
    job_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("production_jobs.id", ondelete="CASCADE"), index=True
    )
    name: Mapped[str] = mapped_column(String(255), default="")
    position: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    trim_height_cm: Mapped[float | None] = mapped_column(Float, nullable=True)
    weight_capacity_kg: Mapped[float | None] = mapped_column(Float, nullable=True)
    notes: Mapped[str] = mapped_column(Text, default="")


class PowerNode(Base):
    """A step in the power tree: a source (mains or a venue outlet), a distro or a breakout.

    A node is fed from its parent through ``feed_connector``, which must be one of the
    parent's ``outputs``. Each output is ``{"connector", "count", "phase"}``; ``phase`` is
    L1, L2 or L3, or null when the output is shared across the phases.
    """

    __tablename__ = "power_nodes"

    id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4)
    job_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("production_jobs.id", ondelete="CASCADE"), index=True
    )
    parent_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("power_nodes.id", ondelete="SET NULL"), nullable=True, index=True
    )
    position: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    kind: Mapped[str] = mapped_column(String(16), nullable=False, default="distro")
    name: Mapped[str] = mapped_column(String(255), default="")
    feed_connector: Mapped[str] = mapped_column(String(64), default="")
    phase: Mapped[str | None] = mapped_column(String(4), nullable=True)
    outputs: Mapped[list] = mapped_column(JSON, default=list, nullable=False)
    rating_amps: Mapped[float | None] = mapped_column(Float, nullable=True)
    active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    venue_outlet_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("venue_power_outlets.id", ondelete="SET NULL"), nullable=True, index=True
    )
    notes: Mapped[str] = mapped_column(Text, default="")
