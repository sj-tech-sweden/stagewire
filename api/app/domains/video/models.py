import uuid
from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Integer, String, Uuid
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.db import Base


class VideoInputList(Base):
    __tablename__ = "video_input_lists"

    id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4)
    job_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("production_jobs.id", ondelete="CASCADE"), index=True
    )
    name: Mapped[str] = mapped_column(String(255), nullable=False, default="Camera inputs")
    position: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    switcher_product_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    switcher_product_name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    switcher_inputs: Mapped[int | None] = mapped_column(Integer, nullable=True)
    switcher_outputs: Mapped[int | None] = mapped_column(Integer, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now()
    )

    inputs: Mapped[list["VideoInput"]] = relationship(
        back_populates="input_list",
        cascade="all, delete-orphan",
        order_by="VideoInput.input_number",
        lazy="selectin",
    )
    outputs: Mapped[list["VideoOutput"]] = relationship(
        back_populates="output_list",
        cascade="all, delete-orphan",
        order_by="VideoOutput.output_number",
        lazy="selectin",
    )


class VideoInput(Base):
    __tablename__ = "video_inputs"

    id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4)
    list_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("video_input_lists.id", ondelete="CASCADE"), index=True
    )
    input_number: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    source_label: Mapped[str] = mapped_column(String(255), default="")
    source_type: Mapped[str] = mapped_column(String(64), default="camera")
    connector: Mapped[str] = mapped_column(String(64), default="sdi")
    notes: Mapped[str] = mapped_column(String(2000), default="")

    input_list: Mapped[VideoInputList] = relationship(back_populates="inputs")
    patch_points: Mapped[list["VideoPatchPoint"]] = relationship(
        back_populates="input",
        cascade="all, delete-orphan",
        order_by="VideoPatchPoint.position",
        lazy="selectin",
    )


class VideoPatchPoint(Base):
    __tablename__ = "video_patch_points"

    id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4)
    input_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("video_inputs.id", ondelete="CASCADE"), index=True
    )
    position: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    connector: Mapped[str] = mapped_column(String(64), default="")
    patch_label: Mapped[str] = mapped_column(String(255), default="")
    notes: Mapped[str] = mapped_column(String(2000), default="")
    device_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("audio_devices.id", ondelete="SET NULL"), nullable=True, index=True
    )

    input: Mapped[VideoInput] = relationship(back_populates="patch_points")


class VideoOutput(Base):
    __tablename__ = "video_outputs"

    id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4)
    list_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("video_input_lists.id", ondelete="CASCADE"), index=True
    )
    output_number: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    name: Mapped[str] = mapped_column(String(255), default="")
    destination_label: Mapped[str] = mapped_column(String(255), default="")
    connector: Mapped[str] = mapped_column(String(64), default="sdi")
    notes: Mapped[str] = mapped_column(String(2000), default="")

    output_list: Mapped[VideoInputList] = relationship(back_populates="outputs")
    patch_points: Mapped[list["VideoOutputPatchPoint"]] = relationship(
        back_populates="output",
        cascade="all, delete-orphan",
        order_by="VideoOutputPatchPoint.position",
        lazy="selectin",
    )


class VideoOutputPatchPoint(Base):
    __tablename__ = "video_output_patch_points"

    id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4)
    output_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("video_outputs.id", ondelete="CASCADE"), index=True
    )
    position: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    connector: Mapped[str] = mapped_column(String(64), default="")
    patch_label: Mapped[str] = mapped_column(String(255), default="")
    notes: Mapped[str] = mapped_column(String(2000), default="")
    device_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("audio_devices.id", ondelete="SET NULL"), nullable=True, index=True
    )

    output: Mapped[VideoOutput] = relationship(back_populates="patch_points")
