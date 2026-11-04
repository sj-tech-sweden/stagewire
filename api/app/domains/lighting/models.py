import uuid

from sqlalchemy import Float, ForeignKey, Integer, String, Text, Uuid
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.db import Base


class FixtureType(Base):
    """A fixture model in the job's library, with its DMX modes and manual physical values."""

    __tablename__ = "fixture_types"

    id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4)
    job_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("production_jobs.id", ondelete="CASCADE"), nullable=True, index=True
    )
    venue_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("venues.id", ondelete="CASCADE"), nullable=True, index=True
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
    venue_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("venues.id", ondelete="CASCADE"), nullable=True, index=True
    )
    fixture_type_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("fixture_types.id", ondelete="CASCADE"), index=True
    )
    name: Mapped[str] = mapped_column(String(128), default="")
    footprint: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    position: Mapped[int] = mapped_column(Integer, nullable=False, default=0)

    fixture_type: Mapped[FixtureType] = relationship(back_populates="modes")
