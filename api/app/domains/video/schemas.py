from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


class VideoPatchPointBase(BaseModel):
    position: int = 0
    connector: str | None = None
    patch_label: str | None = None
    notes: str | None = None
    device_id: UUID | None = None
    source_port: str | None = None
    input_port: str | None = None


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


class VideoOutputPatchPointBase(BaseModel):
    source_port: str | None = None
    input_port: str | None = None
    position: int = 0
    connector: str | None = None
    patch_label: str | None = None
    notes: str | None = None
    device_id: UUID | None = None


class VideoOutputPatchPointCreate(VideoOutputPatchPointBase):
    pass


class VideoOutputPatchPointUpdate(VideoOutputPatchPointBase):
    position: int | None = None


class VideoOutputPatchPointRead(VideoOutputPatchPointBase):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    output_id: UUID
    parent_id: UUID | None = None


class VideoOutputBase(BaseModel):
    output_number: int | None = Field(None, ge=1)
    name: str = ""
    destination_label: str = ""
    connector: str = "sdi"
    notes: str = ""


class VideoOutputCreate(VideoOutputBase):
    pass


class VideoOutputUpdate(VideoOutputBase):
    name: str | None = None
    destination_label: str | None = None
    connector: str | None = None
    notes: str | None = None


class VideoOutputRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    list_id: UUID
    output_number: int
    name: str
    destination_label: str
    connector: str
    notes: str
    patch_points: list[VideoOutputPatchPointRead] = []


class VideoBulkInputs(BaseModel):
    quantity: int = Field(4, ge=1, le=200)
    start_number: int = Field(1, ge=1)
    prefix: str = Field("Cam", max_length=255)
    source_type: str = "camera"
    connector: str = "sdi"
    device_id: UUID | None = None


class VideoBulkOutputs(BaseModel):
    quantity: int = Field(4, ge=1, le=200)
    start_number: int = Field(1, ge=1)
    prefix: str = Field("Out", max_length=255)
    connector: str = "sdi"
    device_id: UUID | None = None


class VideoInputListBase(BaseModel):
    name: str = Field("Camera inputs", max_length=255)


class VideoInputListCreate(VideoInputListBase):
    pass


class VideoInputListUpdate(BaseModel):
    name: str | None = Field(None, max_length=255)
    switcher_product_id: str | None = None
    switcher_product_name: str | None = None
    switcher_inputs: int | None = Field(None, ge=0)
    switcher_outputs: int | None = Field(None, ge=0)


class VideoInputListRead(VideoInputListBase):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    job_id: UUID
    position: int
    switcher_product_id: str | None = None
    switcher_product_name: str | None = None
    switcher_inputs: int | None = None
    switcher_outputs: int | None = None
    inputs: list[VideoInputRead] = []
    outputs: list[VideoOutputRead] = []


class VideoChainStep(BaseModel):
    device_id: UUID
    connector: str | None = ""
    patch_label: str | None = ""
    notes: str | None = ""
    source_port: str | None = ""
    input_port: str | None = ""
    # Index of the earlier step this one takes its signal from. None means it takes it
    # straight from the output. Several steps can share a parent: a split or a passthrough.
    parent_index: int | None = None


class VideoChain(BaseModel):
    steps: list[VideoChainStep] = []


class VideoSheetRow(BaseModel):
    key: str
    list_name: str
    kind: str
    number: int
    label: str
    detail: str
    connector: str
    patch_label: str
    step: int
    steps: int
    notes: str


class VideoSheet(BaseModel):
    device_id: UUID
    name: str
    device_type: str
    rows: list[VideoSheetRow]
