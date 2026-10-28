import uuid
from datetime import datetime

from sqlalchemy import JSON, DateTime, Float, String, Text, Uuid
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
