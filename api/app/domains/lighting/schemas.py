from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


class FixtureBase(BaseModel):
    device_name: str | None = None
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
    dmx_conflict: bool = False
    dmx_overflow: bool = False


class FixtureImportResult(BaseModel):
    created: int = 0
    devices_created: int = 0
    cleared: int = 0
    errors: list[str] = []
