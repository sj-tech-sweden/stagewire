import uuid
from datetime import datetime

from sqlalchemy import DateTime, Float, ForeignKey, Integer, String, Text, Uuid
from sqlalchemy.orm import Mapped, mapped_column, relationship

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
    fixture_type_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("fixture_types.id", ondelete="SET NULL"), nullable=True, index=True
    )
    fixture_mode_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("fixture_modes.id", ondelete="SET NULL"), nullable=True, index=True
    )
    rigging_point_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("rigging_points.id", ondelete="SET NULL"), nullable=True, index=True
    )
    power_node_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("power_nodes.id", ondelete="SET NULL"), nullable=True, index=True
    )
    power_connector: Mapped[str] = mapped_column(String(64), default="")
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now()
    )


class FixtureType(Base):
    """A fixture model in the job's library, with its DMX modes and manual physical values."""

    __tablename__ = "fixture_types"

    id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4)
    job_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("production_jobs.id", ondelete="CASCADE"), index=True
    )
    name: Mapped[str] = mapped_column(String(255), default="")
    manufacturer: Mapped[str] = mapped_column(String(255), default="")
    category: Mapped[str] = mapped_column(String(64), default="")
    source: Mapped[str] = mapped_column(String(32), default="manual")
    stockwire_product_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    weight_kg: Mapped[float | None] = mapped_column(Float, nullable=True)
    power_watts: Mapped[float | None] = mapped_column(Float, nullable=True)
    notes: Mapped[str] = mapped_column(Text, default="")

    modes: Mapped[list["FixtureMode"]] = relationship(
        back_populates="fixture_type",
        cascade="all, delete-orphan",
        order_by="FixtureMode.position",
        lazy="selectin",
    )


class FixtureMode(Base):
    __tablename__ = "fixture_modes"

    id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4)
    fixture_type_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("fixture_types.id", ondelete="CASCADE"), index=True
    )
    name: Mapped[str] = mapped_column(String(128), default="")
    footprint: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    position: Mapped[int] = mapped_column(Integer, nullable=False, default=0)

    fixture_type: Mapped[FixtureType] = relationship(back_populates="modes")


class DmxUniverse(Base):
    """One DMX universe and the output that drives it. Its steps form the chain to the fixtures."""

    __tablename__ = "dmx_universes"

    id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4)
    job_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("production_jobs.id", ondelete="CASCADE"), index=True
    )
    number: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    name: Mapped[str] = mapped_column(String(255), default="")
    source_device_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("audio_devices.id", ondelete="SET NULL"), nullable=True, index=True
    )
    source_port: Mapped[str] = mapped_column(String(32), default="")
    notes: Mapped[str] = mapped_column(Text, default="")


class DmxStep(Base):
    """A device or fixture on a universe. A step's parent is the step it takes DMX from."""

    __tablename__ = "dmx_steps"

    id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4)
    universe_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("dmx_universes.id", ondelete="CASCADE"), index=True
    )
    parent_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("dmx_steps.id", ondelete="SET NULL"), nullable=True, index=True
    )
    position: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    device_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("audio_devices.id", ondelete="SET NULL"), nullable=True, index=True
    )
    fixture_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("lighting_fixtures.id", ondelete="CASCADE"), nullable=True, index=True
    )
    in_port: Mapped[str] = mapped_column(String(32), default="")
    out_port: Mapped[str] = mapped_column(String(32), default="")
    connector: Mapped[str] = mapped_column(String(64), default="")
    notes: Mapped[str] = mapped_column(Text, default="")
