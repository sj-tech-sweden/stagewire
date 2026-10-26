from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


class VideoPatchPointBase(BaseModel):
    position: int = 0
    connector: str | None = None
    patch_label: str | None = None
    notes: str | None = None
    device_id: UUID | None = None


class VideoPatchPointCreate(VideoPatchPointBase):
    pass


class VideoPatchPointUpdate(VideoPatchPointBase):
    position: int | None = None


class VideoPatchPointRead(VideoPatchPointBase):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    input_id: UUID


class VideoInputBase(BaseModel):
    input_number: int | None = Field(None, ge=1)
    source_label: str = ""
    source_type: str = "camera"
    connector: str = "sdi"
    notes: str = ""


class VideoInputCreate(VideoInputBase):
    pass


class VideoInputUpdate(VideoInputBase):
    source_label: str | None = None
    source_type: str | None = None
    connector: str | None = None
    notes: str | None = None


class VideoInputRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    list_id: UUID
    input_number: int
    source_label: str
    source_type: str
    connector: str
    notes: str
    patch_points: list[VideoPatchPointRead] = []


class VideoInputListBase(BaseModel):
    name: str = Field("Camera inputs", max_length=255)


class VideoInputListCreate(VideoInputListBase):
    pass


class VideoInputListUpdate(BaseModel):
    name: str | None = Field(None, max_length=255)


class VideoInputListRead(VideoInputListBase):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    job_id: UUID
    position: int
    inputs: list[VideoInputRead] = []
