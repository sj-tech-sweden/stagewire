from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


class FixtureBase(BaseModel):
    device_name: str | None = None
    fixture_type_id: UUID | None = None
    fixture_mode_id: UUID | None = None
    rigging_point_id: UUID | None = None
    power_circuit_id: UUID | None = None
    universe: int | None = Field(None, ge=1)
    dmx_address: int | None = Field(None, ge=1, le=512)
    fixture_type: str | None = None
    channel_mode: str | None = None
    footprint: int | None = Field(None, ge=1, le=512)
    location: str | None = None
    gel: str | None = None
    purpose: str | None = None
    notes: str | None = None


class FixtureCreate(FixtureBase):
    pass


class FixtureUpdate(FixtureBase):
    pass


class FixtureRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    job_id: UUID
    position: int
    device_id: UUID | None = None
    device_name: str | None = None
    universe: int | None = None
    dmx_address: int | None = None
    fixture_type: str = ""
    channel_mode: str = ""
    footprint: int | None = None
    location: str = ""
    gel: str = ""
    purpose: str = ""
    notes: str = ""
    import_batch_id: UUID | None = None
    fixture_type_id: UUID | None = None
    fixture_mode_id: UUID | None = None
    rigging_point_id: UUID | None = None
    power_circuit_id: UUID | None = None
    dmx_conflict: bool = False
    dmx_overflow: bool = False


class FixtureModeCreate(BaseModel):
    name: str = Field("", max_length=128)
    footprint: int = Field(..., ge=1, le=512)


class FixtureModeUpdate(BaseModel):
    name: str | None = Field(None, max_length=128)
    footprint: int | None = Field(None, ge=1, le=512)


class FixtureModeRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    fixture_type_id: UUID
    name: str
    footprint: int
    position: int = 0


class FixtureTypeBase(BaseModel):
    name: str = ""
    manufacturer: str = ""
    weight_kg: float | None = Field(None, gt=0)
    power_watts: float | None = Field(None, gt=0)
    notes: str = ""


class FixtureTypeCreate(FixtureTypeBase):
    pass


class FixtureTypeUpdate(BaseModel):
    name: str | None = None
    manufacturer: str | None = None
    weight_kg: float | None = Field(None, gt=0)
    power_watts: float | None = Field(None, gt=0)
    notes: str | None = None


class FixtureTypeRead(FixtureTypeBase):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    job_id: UUID
    category: str = ""
    source: str = "manual"
    stockwire_product_id: str | None = None
    modes: list[FixtureModeRead] = []


class StockwireTypeImport(BaseModel):
    product_id: str = Field(..., min_length=1, max_length=64)


class FixtureImportResult(BaseModel):
    created: int = 0
    devices_created: int = 0
    cleared: int = 0
    errors: list[str] = []


class DmxUniverseCreate(BaseModel):
    number: int = Field(1, ge=1)
    name: str = ""
    source_device_id: UUID | None = None
    source_port: str = ""
    notes: str = ""


class DmxUniverseUpdate(BaseModel):
    number: int | None = Field(None, ge=1)
    name: str | None = None
    source_device_id: UUID | None = None
    source_port: str | None = None
    notes: str | None = None


class DmxStepCreate(BaseModel):
    """A device or a fixture on a universe. Exactly one of device_id and fixture_id is set."""

    parent_id: UUID | None = None
    device_id: UUID | None = None
    fixture_id: UUID | None = None
    in_port: str = ""
    out_port: str = ""
    connector: str = ""
    notes: str = ""


class DmxStepUpdate(BaseModel):
    parent_id: UUID | None = None
    in_port: str | None = None
    out_port: str | None = None
    connector: str | None = None
    notes: str | None = None


class PowerStepCreate(BaseModel):
    device_id: UUID | None = None
    label: str = ""
    connector_in: str = ""
    connector_out: str = ""
    notes: str = ""


class PowerStepUpdate(BaseModel):
    device_id: UUID | None = None
    label: str | None = None
    connector_in: str | None = None
    connector_out: str | None = None
    notes: str | None = None


class PowerStepRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    fixture_id: UUID
    position: int = 0
    device_id: UUID | None = None
    label: str = ""
    connector_in: str = ""
    connector_out: str = ""
    notes: str = ""
