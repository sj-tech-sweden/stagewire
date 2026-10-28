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

    channel_lists: Mapped[list["ChannelList"]] = relationship(
        back_populates="job",
        cascade="all, delete-orphan",
        order_by="ChannelList.position",
    )
    plot_elements: Mapped[list["StagePlotElement"]] = relationship(
        back_populates="job", cascade="all, delete-orphan"
    )
    devices: Mapped[list["AudioDevice"]] = relationship(
        back_populates="job", cascade="all, delete-orphan", order_by="AudioDevice.position"
    )


class ChannelList(Base):
    __tablename__ = "audio_channel_lists"

    id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4)
    job_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("production_jobs.id", ondelete="CASCADE"), index=True
    )
    name: Mapped[str] = mapped_column(String(255), nullable=False, default="Input List")
    position: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now()
    )
    mixer_product_id: Mapped[str | None] = mapped_column(String(64), nullable=True, index=True)
    mixer_product_name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    mixer_inputs: Mapped[int | None] = mapped_column(Integer, nullable=True)
    mixer_buses: Mapped[int | None] = mapped_column(Integer, nullable=True)

    job: Mapped[ProductionJob] = relationship(back_populates="channel_lists")
    channels: Mapped[list["AudioChannelPatch"]] = relationship(
        back_populates="channel_list",
        cascade="all, delete-orphan",
        order_by="AudioChannelPatch.channel_number",
        lazy="selectin",
    )
    outputs: Mapped[list["ChannelListOutput"]] = relationship(
        back_populates="channel_list",
        cascade="all, delete-orphan",
        order_by="ChannelListOutput.position",
        lazy="selectin",
    )


class AudioChannelPatch(Base):
    __tablename__ = "audio_channel_patches"

    id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4)
    channel_list_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("audio_channel_lists.id", ondelete="CASCADE"), index=True
    )
    channel_number: Mapped[int] = mapped_column(Integer, nullable=False)
    source_label: Mapped[str] = mapped_column(String(255), default="")
    input_type: Mapped[str | None] = mapped_column(String(64), nullable=True)
    connector: Mapped[str | None] = mapped_column(String(64), nullable=True)
    device: Mapped[str | None] = mapped_column(String(255), nullable=True)
    stand_type: Mapped[str] = mapped_column(String(255), default="")
    instrument_group: Mapped[str] = mapped_column(
        String(32), default="other", server_default="other"
    )
    performer_name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    wireless_pack: Mapped[str | None] = mapped_column(String(255), nullable=True)
    wireless_frequency: Mapped[str | None] = mapped_column(String(64), nullable=True)
    phantom_power: Mapped[bool] = mapped_column(Boolean, default=False)
    stereo: Mapped[bool] = mapped_column(Boolean, default=False)
    stereo_channel: Mapped[int | None] = mapped_column(Integer, nullable=True)
    notes: Mapped[str] = mapped_column(String(2000), default="")
    color_code: Mapped[str | None] = mapped_column(String(32), nullable=True)
    stockwire_asset_id: Mapped[str | None] = mapped_column(String(255), nullable=True)
    stockwire_product_id: Mapped[str | None] = mapped_column(String(64), nullable=True, index=True)
    stockwire_product_name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    stand_product_id: Mapped[str | None] = mapped_column(String(64), nullable=True, index=True)
    stand_product_name: Mapped[str | None] = mapped_column(String(255), nullable=True)

    channel_list: Mapped[ChannelList] = relationship(back_populates="channels")
    patch_points: Mapped[list["ChannelPatchPoint"]] = relationship(
        back_populates="channel",
        cascade="all, delete-orphan",
        order_by="ChannelPatchPoint.position",
        lazy="selectin",
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
    sound_list_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("audio_channel_lists.id", ondelete="SET NULL"), nullable=True, index=True
    )
    video_list_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("video_input_lists.id", ondelete="SET NULL"), nullable=True, index=True
    )
    sensor_width_mm: Mapped[float | None] = mapped_column(Float, nullable=True)
    focal_min_mm: Mapped[float | None] = mapped_column(Float, nullable=True)
    focal_max_mm: Mapped[float | None] = mapped_column(Float, nullable=True)
    max_distance_m: Mapped[float | None] = mapped_column(Float, nullable=True)
    throw_ratio_min: Mapped[float | None] = mapped_column(Float, nullable=True)
    throw_ratio_max: Mapped[float | None] = mapped_column(Float, nullable=True)
    image_aspect_ratio: Mapped[float | None] = mapped_column(Float, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now()
    )

    job: Mapped[ProductionJob] = relationship(back_populates="devices")
    patch_points: Mapped[list["ChannelPatchPoint"]] = relationship(
        back_populates="device",
        order_by="ChannelPatchPoint.position",
        lazy="selectin",
    )
    output_points: Mapped[list["OutputPatchPoint"]] = relationship(
        back_populates="device",
        lazy="selectin",
    )


class StagePlotElement(Base):
    __tablename__ = "stage_plot_elements"

    id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4)
    job_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("production_jobs.id", ondelete="CASCADE"), index=True
    )
    linked_channel_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("audio_channel_patches.id", ondelete="SET NULL"), nullable=True
    )
    linked_patch_point_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("channel_patch_points.id", ondelete="SET NULL"), nullable=True
    )
    linked_device_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("audio_devices.id", ondelete="SET NULL"), nullable=True
    )
    linked_output_point_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("output_patch_points.id", ondelete="SET NULL"), nullable=True
    )
    linked_video_input_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("video_inputs.id", ondelete="SET NULL"), nullable=True
    )
    linked_lens_device_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("audio_devices.id", ondelete="SET NULL"), nullable=True
    )
    focal_mm: Mapped[float | None] = mapped_column(Float, nullable=True)
    element_type: Mapped[str] = mapped_column(String(64), nullable=False)
    position_x: Mapped[float] = mapped_column(Float, default=0.0)
    position_y: Mapped[float] = mapped_column(Float, default=0.0)
    rotation: Mapped[float] = mapped_column(Float, default=0.0)
    width_cm: Mapped[float] = mapped_column(Float, default=60.0)
    height_cm: Mapped[float] = mapped_column(Float, default=60.0)
    label: Mapped[str] = mapped_column(String(255), default="")
    image_url: Mapped[str] = mapped_column(String(1024), default="")
    coverage_angle_h: Mapped[float] = mapped_column(Float, default=0.0)
    coverage_distance_m: Mapped[float] = mapped_column(Float, default=0.0)

    job: Mapped[ProductionJob] = relationship(back_populates="plot_elements")


class ChannelPatchPoint(Base):
    __tablename__ = "channel_patch_points"

    id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4)
    channel_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("audio_channel_patches.id", ondelete="CASCADE"), index=True
    )
    position: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    point_type: Mapped[str] = mapped_column(String(64), nullable=False, default="mixer")
    connector: Mapped[str] = mapped_column(String(64), default="")
    patch_label: Mapped[str] = mapped_column(String(255), default="")
    notes: Mapped[str] = mapped_column(String(2000), default="")
    device_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("audio_devices.id", ondelete="SET NULL"), nullable=True, index=True
    )

    channel: Mapped[AudioChannelPatch] = relationship(back_populates="patch_points")
    device: Mapped["AudioDevice"] = relationship(back_populates="patch_points")


class ChannelListOutput(Base):
    __tablename__ = "channel_list_outputs"

    id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4)
    channel_list_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("audio_channel_lists.id", ondelete="CASCADE"), index=True
    )
    name: Mapped[str] = mapped_column(String(255), nullable=False, default="Output")
    position: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    mode: Mapped[str] = mapped_column(String(32), nullable=False, default="mono")
    connector: Mapped[str | None] = mapped_column(String(64), nullable=True)
    notes: Mapped[str] = mapped_column(String(2000), default="")
    color_code: Mapped[str | None] = mapped_column(String(32), nullable=True)

    channel_list: Mapped[ChannelList] = relationship(back_populates="outputs")
    points: Mapped[list["OutputPatchPoint"]] = relationship(
        back_populates="output",
        cascade="all, delete-orphan",
        order_by="OutputPatchPoint.position",
        lazy="selectin",
    )


class OutputPatchPoint(Base):
    __tablename__ = "output_patch_points"

    id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4)
    output_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("channel_list_outputs.id", ondelete="CASCADE"), index=True
    )
    position: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    point_type: Mapped[str] = mapped_column(String(64), nullable=False, default="mixer")
    connector: Mapped[str] = mapped_column(String(64), default="")
    patch_label: Mapped[str] = mapped_column(String(255), default="")
    notes: Mapped[str] = mapped_column(String(2000), default="")
    parallel: Mapped[bool] = mapped_column(Boolean, default=False)
    parent_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("output_patch_points.id", ondelete="SET NULL"), nullable=True
    )
    bus_connector: Mapped[str | None] = mapped_column(String(32), nullable=True)
    device_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("audio_devices.id", ondelete="SET NULL"), nullable=True, index=True
    )

    output: Mapped[ChannelListOutput] = relationship(back_populates="points")
    device: Mapped["AudioDevice"] = relationship(back_populates="output_points")


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
