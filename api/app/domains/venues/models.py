import uuid
from datetime import datetime

from sqlalchemy import JSON, DateTime, Float, ForeignKey, Integer, String, Text, Uuid
from sqlalchemy.orm import Mapped, mapped_column

from app.core.db import Base


class Venue(Base):
    """A reusable venue template (shared across all users).

    Jobs copy these dimensions when a venue is assigned, so editing a venue only
    changes other jobs when it is explicitly propagated.
    """

    __tablename__ = "venues"

    id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    notes: Mapped[str] = mapped_column(Text, default="", nullable=False)
    venue_width_cm: Mapped[float] = mapped_column(Float, default=0.0)
    venue_height_cm: Mapped[float] = mapped_column(Float, default=0.0)
    stage_x_cm: Mapped[float] = mapped_column(Float, default=0.0)
    stage_y_cm: Mapped[float] = mapped_column(Float, default=0.0)
    stage_width_cm: Mapped[float] = mapped_column(Float, default=0.0)
    stage_height_cm: Mapped[float] = mapped_column(Float, default=0.0)
    background_image_url: Mapped[str] = mapped_column(String(1024), default="", nullable=False)
    audience_polygon: Mapped[list] = mapped_column(JSON, default=list, nullable=False)
    propagated_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(), onupdate=lambda: datetime.now()
    )


class VenuePowerGroup(Base):
    """A circuit of the venue's power: one fuse/breaker feeding several outlets.

    The group's rating is shared by every load on its outlets, so the power tree treats a used
    group as one source with the group's rating and one output per outlet connector.
    """

    __tablename__ = "venue_power_groups"

    id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4)
    venue_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("venues.id", ondelete="CASCADE"), index=True
    )
    name: Mapped[str] = mapped_column(String(255), default="")
    rating_amps: Mapped[float | None] = mapped_column(Float, nullable=True)
    phases: Mapped[int] = mapped_column(Integer, default=1, nullable=False)
    # Which phase a one-phase group is on (L1 when not set); a three-phase group spreads its load.
    phase: Mapped[str | None] = mapped_column(String(2), nullable=True)
    notes: Mapped[str] = mapped_column(Text, default="")


class VenuePowerOutlet(Base):
    """A mains outlet that belongs to a venue, and where it sits on the stage plot (cm)."""

    __tablename__ = "venue_power_outlets"

    id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4)
    venue_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("venues.id", ondelete="CASCADE"), index=True
    )
    name: Mapped[str] = mapped_column(String(255), default="")
    connector: Mapped[str] = mapped_column(String(64), default="")
    rating_amps: Mapped[float | None] = mapped_column(Float, nullable=True)
    group_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("venue_power_groups.id", ondelete="SET NULL"), nullable=True, index=True
    )
    x_cm: Mapped[float | None] = mapped_column(Float, nullable=True)
    y_cm: Mapped[float | None] = mapped_column(Float, nullable=True)
    notes: Mapped[str] = mapped_column(Text, default="")
