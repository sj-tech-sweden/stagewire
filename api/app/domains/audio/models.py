import uuid
from datetime import datetime

from sqlalchemy import (
    JSON,
    DateTime,
    Float,
    ForeignKey,
    Integer,
    String,
    Text,
    UniqueConstraint,
    Uuid,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.db import Base


class ProductionJob(Base):
    __tablename__ = "production_jobs"

    id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4)
    stockwire_job_id: Mapped[str | None] = mapped_column(String(255), nullable=True, index=True)
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    venue_name: Mapped[str] = mapped_column(String(255), default="")
    event_date: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    notes: Mapped[str] = mapped_column(Text, default="", nullable=False)
    stage_width_cm: Mapped[float] = mapped_column(Float, default=0.0)
    stage_height_cm: Mapped[float] = mapped_column(Float, default=0.0)
    venue_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("venues.id", ondelete="SET NULL"), nullable=True, index=True
    )
    venue_width_cm: Mapped[float] = mapped_column(Float, default=0.0)
    venue_height_cm: Mapped[float] = mapped_column(Float, default=0.0)
    stage_x_cm: Mapped[float] = mapped_column(Float, default=0.0)
    stage_y_cm: Mapped[float] = mapped_column(Float, default=0.0)
    venue_background_image_url: Mapped[str] = mapped_column(String(1024), default="")
    audience_polygon: Mapped[list] = mapped_column(JSON, default=list)
    cable_plan: Mapped[dict] = mapped_column(JSON, default=dict)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now()
    )

    devices: Mapped[list["AudioDevice"]] = relationship(
        back_populates="job", cascade="all, delete-orphan", order_by="AudioDevice.position"
    )


class AudioDevice(Base):
    """A physical box in the signal chain (stagebox, mixer, split, etc.).

    Groups all the patch points that belong to one physical unit so a stage-plot
    element can be linked to the whole box instead of a single connector.
    """

    __tablename__ = "audio_devices"

    id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4)
    job_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("production_jobs.id", ondelete="CASCADE"), index=True
    )
    name: Mapped[str] = mapped_column(String(255), default="")
    device_type: Mapped[str] = mapped_column(String(64), default="other")
    position: Mapped[int] = mapped_column(Integer, default=0)
    notes: Mapped[str] = mapped_column(Text, default="")
    ports: Mapped[list] = mapped_column(JSON, default=list)
    stockwire_product_id: Mapped[str | None] = mapped_column(String(64), nullable=True, index=True)
    stockwire_product_name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    input_override: Mapped[int | None] = mapped_column(Integer, nullable=True)
    output_override: Mapped[int | None] = mapped_column(Integer, nullable=True)
    # The public id of the device's sound list node (see graph/ids.py); not a foreign key, channel
    # lists live on the graph. Deleting a list clears it (audio_native.delete_node_tree).
    sound_list_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid(as_uuid=True), nullable=True, index=True
    )
    # The public id of the device's video list node (see graph/ids.py); not a foreign key, a
    # list made in the graph has no row in video_input_lists.
    video_list_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid(as_uuid=True), nullable=True, index=True
    )
    sensor_width_mm: Mapped[float | None] = mapped_column(Float, nullable=True)
    focal_min_mm: Mapped[float | None] = mapped_column(Float, nullable=True)
    focal_max_mm: Mapped[float | None] = mapped_column(Float, nullable=True)
    max_distance_m: Mapped[float | None] = mapped_column(Float, nullable=True)
    throw_ratio_min: Mapped[float | None] = mapped_column(Float, nullable=True)
    throw_ratio_max: Mapped[float | None] = mapped_column(Float, nullable=True)
    image_aspect_ratio: Mapped[float | None] = mapped_column(Float, nullable=True)
    weight_kg: Mapped[float | None] = mapped_column(Float, nullable=True)
    power_watts: Mapped[float | None] = mapped_column(Float, nullable=True)
    fixture_type: Mapped[str | None] = mapped_column(String(64), nullable=True)
    channel_mode: Mapped[str | None] = mapped_column(String(64), nullable=True)
    footprint_channels: Mapped[int | None] = mapped_column(Integer, nullable=True)
    default_gel: Mapped[str | None] = mapped_column(String(32), nullable=True)
    # How the device takes mains: its own inlet (iec_c13, attached_schuko, powercon, ...), and which
    # power node output it is plugged into. Fixtures and plot elements are plugged through their
    # own rows (see rigging.service.collect_loads); a plain device is a load through these.
    power_inlet: Mapped[str] = mapped_column(String(32), default="", nullable=False)
    # the public id of the power node the device is plugged into (graph/ids.py); not a foreign key,
    # power nodes live on the graph
    power_node_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid(as_uuid=True),
        nullable=True,
        index=True,
    )
    power_connector: Mapped[str] = mapped_column(String(64), default="", nullable=False)
    # Where a device that is hung (an LED wall, a screen) hangs; fixtures and plot elements carry
    # their own rigging point.
    # the public id of the rigging point node (graph/ids.py); not a foreign key, rigging points
    # live on the graph
    rigging_point_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid(as_uuid=True), nullable=True, index=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now()
    )

    job: Mapped[ProductionJob] = relationship(back_populates="devices")


class StockwireRequirementLink(Base):
    """Maps one product in a Stagewire job to the stockwire-rental requirement for it.

    One row per product: ``quantity`` is the number of patch slots using it.
    """

    __tablename__ = "stockwire_requirement_links"
    __table_args__ = (UniqueConstraint("job_id", "item_key", name="uq_stockwire_link_job_item"),)

    id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4)
    job_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("production_jobs.id", ondelete="CASCADE"), index=True
    )
    item_key: Mapped[str] = mapped_column(String(255), nullable=False)
    product_id: Mapped[str] = mapped_column(String(64), nullable=False)
    product_name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    rental_requirement_id: Mapped[int] = mapped_column(Integer, nullable=False)
    quantity: Mapped[int] = mapped_column(Integer, nullable=False, default=1, server_default="1")
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now()
    )
