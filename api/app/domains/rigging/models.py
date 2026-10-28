import uuid

from sqlalchemy import Float, ForeignKey, Integer, String, Text, Uuid
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


class PowerDistro(Base):
    """A distribution box or supply. Circuits are patched from it, one phase each."""

    __tablename__ = "power_distros"

    id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4)
    job_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("production_jobs.id", ondelete="CASCADE"), index=True
    )
    name: Mapped[str] = mapped_column(String(255), default="")
    position: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    voltage: Mapped[int] = mapped_column(Integer, nullable=False, default=230)
    amps_per_phase: Mapped[float | None] = mapped_column(Float, nullable=True)
    notes: Mapped[str] = mapped_column(Text, default="")


class PowerCircuit(Base):
    __tablename__ = "power_circuits"

    id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4)
    distro_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("power_distros.id", ondelete="CASCADE"), index=True
    )
    label: Mapped[str] = mapped_column(String(255), default="")
    phase: Mapped[str] = mapped_column(String(4), nullable=False, default="L1")
    breaker_amps: Mapped[float | None] = mapped_column(Float, nullable=True)
    position: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    notes: Mapped[str] = mapped_column(Text, default="")
