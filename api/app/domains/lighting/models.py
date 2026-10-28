import uuid
from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Integer, String, Text, Uuid
from sqlalchemy.orm import Mapped, mapped_column

from app.core.db import Base


class LightingFixture(Base):
    """One patched fixture: a row on the job's DMX patch sheet."""

    __tablename__ = "lighting_fixtures"

    id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4)
    job_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("production_jobs.id", ondelete="CASCADE"), index=True
    )
    position: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    device_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("audio_devices.id", ondelete="SET NULL"), nullable=True, index=True
    )
    universe: Mapped[int | None] = mapped_column(Integer, nullable=True)
    dmx_address: Mapped[int | None] = mapped_column(Integer, nullable=True)
    fixture_type: Mapped[str] = mapped_column(String(64), default="")
    channel_mode: Mapped[str] = mapped_column(String(64), default="")
    footprint: Mapped[int | None] = mapped_column(Integer, nullable=True)
    location: Mapped[str] = mapped_column(String(255), default="")
    gel: Mapped[str] = mapped_column(String(32), default="")
    purpose: Mapped[str] = mapped_column(String(255), default="")
    notes: Mapped[str] = mapped_column(Text, default="")
    import_batch_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid(as_uuid=True), nullable=True, index=True
    )
    rigging_point_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("rigging_points.id", ondelete="SET NULL"), nullable=True, index=True
    )
    power_circuit_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("power_circuits.id", ondelete="SET NULL"), nullable=True, index=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now()
    )
