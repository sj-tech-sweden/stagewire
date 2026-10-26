from datetime import datetime
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


class ProductionJobBase(BaseModel):
    title: str = Field(..., max_length=255)
    venue_name: str = ""
    event_date: datetime | None = None
    stockwire_job_id: str | None = None
    notes: str = ""
    stage_width_cm: float = 0.0
    stage_height_cm: float = 0.0
    venue_width_cm: float = 0.0
    venue_height_cm: float = 0.0
    stage_x_cm: float = 0.0
    stage_y_cm: float = 0.0
    venue_background_image_url: str = ""
    cable_plan: dict = Field(default_factory=dict)


class ProductionJobCreate(ProductionJobBase):
    pass


class ProductionJobUpdate(BaseModel):
    title: str | None = None
    venue_name: str | None = None
    event_date: datetime | None = None
    stockwire_job_id: str | None = None
    notes: str | None = None
    stage_width_cm: float | None = Field(None, ge=0)
    stage_height_cm: float | None = Field(None, ge=0)
    stage_x_cm: float | None = Field(None, ge=0)
    stage_y_cm: float | None = Field(None, ge=0)
    venue_width_cm: float | None = Field(None, ge=0)
    venue_height_cm: float | None = Field(None, ge=0)
    cable_plan: dict | None = None


class ProductionJobRead(ProductionJobBase):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    venue_id: UUID | None = None
    created_at: datetime


class AudioChannelPatchBase(BaseModel):
    channel_number: int
    source_label: str = ""
    input_type: str | None = None
    connector: str | None = None
    device: str | None = None
    stand_type: str = ""
    instrument_group: Literal[
        "drums", "percussion", "bass", "guitars", "keys", "brass", "vocals", "playback", "other"
    ] = "other"
    performer_name: str | None = None
    wireless_pack: str | None = None
    wireless_frequency: str | None = None
    phantom_power: bool = False
    stereo: bool = False
    stereo_channel: int | None = None
    notes: str = ""
    color_code: str | None = None
    stockwire_asset_id: str | None = None
    stockwire_product_id: str | None = None
    stockwire_product_name: str | None = None
    stand_product_id: str | None = None
    stand_product_name: str | None = None


class AudioChannelPatchCreate(AudioChannelPatchBase):
    pass


class AudioChannelPatchUpdate(AudioChannelPatchBase):
    channel_number: int | None = None


class AudioChannelPatchRead(AudioChannelPatchBase):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    channel_list_id: UUID
    patch_points: list["ChannelPatchPointRead"] = []


class ChannelPatchPointBase(BaseModel):
    position: int = 0
    point_type: str | None = None
    connector: str | None = None
    patch_label: str | None = None
    notes: str | None = None
    device_id: UUID | None = None


class ChannelPatchPointCreate(ChannelPatchPointBase):
    pass


class ChannelPatchPointUpdate(ChannelPatchPointBase):
    position: int | None = None
    point_type: str | None = None


class ChannelPatchPointRead(ChannelPatchPointBase):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    channel_id: UUID


class OutputPatchPointBase(BaseModel):
    position: int = 0
    point_type: str | None = None
    connector: str | None = None
    patch_label: str | None = None
    notes: str | None = None
    parallel: bool = False
    parent_id: UUID | None = None
    bus_connector: str | None = None
    device_id: UUID | None = None


class OutputPatchPointCreate(OutputPatchPointBase):
    pass


class OutputPatchPointUpdate(OutputPatchPointBase):
    position: int | None = None
    point_type: str | None = None


class OutputPatchPointRead(OutputPatchPointBase):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    output_id: UUID


class ChannelListOutputBase(BaseModel):
    name: str = "Output"
    position: int = 0
    mode: str = "mono"
    connector: str | None = None
    notes: str = ""
    color_code: str | None = None


class ChannelListOutputCreate(ChannelListOutputBase):
    pass


class ChannelListOutputUpdate(ChannelListOutputBase):
    name: str | None = None
    position: int | None = None
    connector: str | None = None
    notes: str | None = None
    color_code: str | None = None


class ChannelListOutputRead(ChannelListOutputBase):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    channel_list_id: UUID
    points: list[OutputPatchPointRead] = []


class PatchSheetChannel(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    kind: str = "channel"
    channel_id: UUID
    channel_number: int
    source_label: str
    output_name: str | None = None
    input_type: str | None = None
    device: str | None = None
    phantom_power: bool = False
    notes: str = ""
    direction: str = "in"
    chain_label: str | None = None
    point: ChannelPatchPointRead


class PatchSheetRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    name: str
    device_id: UUID
    point_type: str
    channels: list[PatchSheetChannel] = []


class ChannelListBase(BaseModel):
    name: str
    position: int = 0
    mixer_product_id: str | None = None
    mixer_product_name: str | None = None
    mixer_inputs: int | None = None
    mixer_buses: int | None = None


class ChannelListCreate(ChannelListBase):
    pass


class ChannelListUpdate(ChannelListBase):
    name: str | None = None
    position: int | None = None
    mixer_product_id: str | None = None
    mixer_product_name: str | None = None
    mixer_inputs: int | None = None
    mixer_buses: int | None = None


class ChannelListRead(ChannelListBase):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    job_id: UUID
    created_at: datetime
    channels: list[AudioChannelPatchRead] = []
    outputs: list[ChannelListOutputRead] = []


class ExportPluginInfo(BaseModel):
    key: str
    label: str
    description: str
    media_type: str
    file_extension: str


class StagePlotElementBase(BaseModel):
    element_type: str
    linked_channel_id: UUID | None = None
    linked_patch_point_id: UUID | None = None
    linked_device_id: UUID | None = None
    position_x: float = 0.0
    position_y: float = 0.0
    rotation: float = 0.0
    width_cm: float = 60.0
    height_cm: float = 60.0
    label: str = ""
    image_url: str = ""
    linked_output_point_id: UUID | None = None
    linked_video_input_id: UUID | None = None
    coverage_angle_h: float = 0.0
    coverage_distance_m: float = 0.0


class StagePlotElementCreate(StagePlotElementBase):
    pass


class StagePlotElementUpdate(StagePlotElementBase):
    element_type: str | None = None


class StagePlotElementRead(StagePlotElementBase):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    job_id: UUID


class AudioDevicePort(BaseModel):
    direction: str = "in"  # 'in' | 'out'
    connector: str = ""
    count: int = 0


class AudioDeviceBase(BaseModel):
    name: str = ""
    device_type: str = "other"
    position: int = 0
    notes: str = ""
    ports: list[AudioDevicePort] | None = []
    stockwire_product_id: str | None = None
    stockwire_product_name: str | None = None


class AudioDeviceCreate(AudioDeviceBase):
    pass


class AudioDeviceUpdate(AudioDeviceBase):
    name: str | None = None
    device_type: str | None = None
    position: int | None = None
    notes: str | None = None
    input_override: int | None = Field(None, ge=0)
    output_override: int | None = Field(None, ge=0)


class AudioDeviceRead(AudioDeviceBase):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    job_id: UUID
    patch_point_count: int = 0
    input_override: int | None = None
    output_override: int | None = None
    input_default: int | None = None
    output_default: int | None = None
    input_count: int | None = None
    output_count: int | None = None


__all__ = [
    "ProductionJobBase",
    "ProductionJobCreate",
    "ProductionJobUpdate",
    "ProductionJobRead",
    "AudioChannelPatchBase",
    "AudioChannelPatchCreate",
    "AudioChannelPatchUpdate",
    "AudioChannelPatchRead",
    "ChannelPatchPointBase",
    "ChannelPatchPointCreate",
    "ChannelPatchPointUpdate",
    "ChannelPatchPointRead",
    "OutputPatchPointBase",
    "OutputPatchPointCreate",
    "OutputPatchPointUpdate",
    "OutputPatchPointRead",
    "ChannelListOutputBase",
    "ChannelListOutputCreate",
    "ChannelListOutputUpdate",
    "ChannelListOutputRead",
    "PatchSheetChannel",
    "PatchSheetRead",
    "ExportPluginInfo",
    "StagePlotElementBase",
    "StagePlotElementCreate",
    "StagePlotElementUpdate",
    "StagePlotElementRead",
    "AudioDeviceBase",
    "AudioDeviceCreate",
    "AudioDeviceUpdate",
    "AudioDeviceRead",
]

AudioChannelPatchRead.model_rebuild()
ChannelListOutputRead.model_rebuild()
