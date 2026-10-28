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


class PowerDistroBase(BaseModel):
    name: str = ""
    voltage: int = Field(230, gt=0)
    amps_per_phase: float | None = Field(None, gt=0)
    notes: str = ""


class PowerDistroCreate(PowerDistroBase):
    pass


class PowerDistroUpdate(PowerDistroBase):
    pass


class PowerDistroRead(PowerDistroBase):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    job_id: UUID
    position: int = 0


class PowerCircuitBase(BaseModel):
    label: str = ""
    phase: Literal["L1", "L2", "L3"] = "L1"
    breaker_amps: float | None = Field(None, gt=0)
    notes: str = ""


class PowerCircuitCreate(PowerCircuitBase):
    distro_id: UUID


class PowerCircuitUpdate(PowerCircuitBase):
    label: str | None = None
    phase: Literal["L1", "L2", "L3"] | None = None


class PowerCircuitRead(PowerCircuitBase):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    distro_id: UUID
    position: int = 0


class LoadRead(BaseModel):
    id: UUID
    kind: Literal["fixture", "element"]
    label: str
    weight_kg: float | None = None
    power_w: float | None = None
    rigging_point_id: UUID | None = None
    power_circuit_id: UUID | None = None


class LoadAssign(BaseModel):
    rigging_point_id: UUID | None = None
    power_circuit_id: UUID | None = None
