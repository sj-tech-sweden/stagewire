from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


class RiggingPointBase(BaseModel):
    name: str = ""
    trim_height_cm: float | None = Field(None, gt=0)
    weight_capacity_kg: float | None = Field(None, gt=0)
    notes: str = ""


class RiggingPointCreate(RiggingPointBase):
    pass


class RiggingPointUpdate(RiggingPointBase):
    pass


class RiggingPointRead(RiggingPointBase):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    job_id: UUID
    position: int = 0


class PowerOutput(BaseModel):
    connector: str
    count: int = Field(1, ge=1, le=99)
    phase: Literal["L1", "L2", "L3"] | None = None


class PowerNodeBase(BaseModel):
    name: str = ""
    kind: Literal["source", "distro", "breakout"] = "distro"
    feed_connector: str = ""
    phase: Literal["L1", "L2", "L3"] | None = None
    outputs: list[PowerOutput] = []
    rating_amps: float | None = Field(None, gt=0)
    active: bool = True
    venue_outlet_id: UUID | None = None
    device_id: UUID | None = None
    notes: str = ""


class PowerNodeCreate(PowerNodeBase):
    parent_id: UUID | None = None


class PowerNodeUpdate(BaseModel):
    name: str | None = None
    kind: Literal["source", "distro", "breakout"] | None = None
    parent_id: UUID | None = None
    feed_connector: str | None = None
    phase: Literal["L1", "L2", "L3"] | None = None
    outputs: list[PowerOutput] | None = None
    rating_amps: float | None = Field(None, gt=0)
    active: bool | None = None
    venue_outlet_id: UUID | None = None
    device_id: UUID | None = None
    notes: str | None = None


class PowerNodeRead(PowerNodeBase):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    job_id: UUID
    parent_id: UUID | None = None
    position: int = 0


class LoadRead(BaseModel):
    id: UUID
    kind: Literal["fixture", "element"]
    label: str
    device_id: UUID | None = None
    weight_kg: float | None = None
    power_w: float | None = None
    rigging_point_id: UUID | None = None
    power_node_id: UUID | None = None
    power_connector: str = ""


class LoadAssign(BaseModel):
    rigging_point_id: UUID | None = None
    power_node_id: UUID | None = None
    power_connector: str | None = None
