from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, model_validator


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
    """A single-phase circuit sits on one phase; a three-phase circuit spreads over L1-L3.

    Breaker rating is per line in both cases.
    """

    label: str = ""
    phases: Literal[1, 3] = 1
    phase: Literal["L1", "L2", "L3"] | None = "L1"
    breaker_amps: float | None = Field(None, gt=0)
    notes: str = ""

    @model_validator(mode="after")
    def _phase_for_single_phase(self):
        if self.phases == 1 and self.phase is None:
            self.phase = "L1"
        if self.phases == 3:
            self.phase = None
        return self


class PowerCircuitCreate(PowerCircuitBase):
    distro_id: UUID


class PowerCircuitUpdate(BaseModel):
    label: str | None = None
    phases: Literal[1, 3] | None = None
    phase: Literal["L1", "L2", "L3"] | None = None
    breaker_amps: float | None = Field(None, gt=0)
    notes: str | None = None


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
