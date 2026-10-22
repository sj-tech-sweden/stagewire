from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


class ProductionJobBase(BaseModel):
    title: str = Field(..., max_length=255)
    venue_name: str = ""
    event_date: datetime | None = None
    stockwire_job_id: str | None = None
    notes: str = ""


class ProductionJobCreate(ProductionJobBase):
    pass


class ProductionJobUpdate(BaseModel):
    title: str | None = None
    venue_name: str | None = None
    event_date: datetime | None = None
    stockwire_job_id: str | None = None
    notes: str | None = None


class ProductionJobRead(ProductionJobBase):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    created_at: datetime


class AudioChannelPatchBase(BaseModel):
    channel_number: int
    source_label: str = ""
    input_type: str | None = None
    connector: str | None = None
    device: str | None = None
    transducer: str = ""
    stand_type: str = ""
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
    name: str | None = None
    connector: str | None = None
    patch_label: str | None = None
    notes: str | None = None
    stockwire_product_id: str | None = None
    stockwire_product_name: str | None = None


class ChannelPatchPointCreate(ChannelPatchPointBase):
    pass


class ChannelPatchPointUpdate(ChannelPatchPointBase):
    position: int | None = None
    point_type: str | None = None
    name: str | None = None


class ChannelPatchPointRead(ChannelPatchPointBase):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    channel_id: UUID


class OutputPatchPointBase(BaseModel):
    position: int = 0
    point_type: str | None = None
    name: str | None = None
    connector: str | None = None
    patch_label: str | None = None
    notes: str | None = None
    parallel: bool = False
    parent_id: UUID | None = None
    bus_connector: str | None = None
    stockwire_product_id: str | None = None
    stockwire_product_name: str | None = None


class OutputPatchPointCreate(OutputPatchPointBase):
    pass


class OutputPatchPointUpdate(OutputPatchPointBase):
    position: int | None = None
    point_type: str | None = None
    name: str | None = None


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


class StagePlotElementBase(BaseModel):
    element_type: str
    linked_channel_id: UUID | None = None
    position_x: float = 0.0
    position_y: float = 0.0
    rotation: float = 0.0
    label: str = ""


class StagePlotElementCreate(StagePlotElementBase):
    pass


class StagePlotElementUpdate(StagePlotElementBase):
    element_type: str | None = None


class StagePlotElementRead(StagePlotElementBase):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    job_id: UUID


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
    "StagePlotElementBase",
    "StagePlotElementCreate",
    "StagePlotElementUpdate",
    "StagePlotElementRead",
]

AudioChannelPatchRead.model_rebuild()
ChannelListOutputRead.model_rebuild()
