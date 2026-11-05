from datetime import datetime
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.domains.audio.polygon import check_polygon
from app.domains.graph.schemas import Domain, Port, Signal

FootprintShape = Literal["rectangular", "arena_circular", "amphitheater", "custom_polygon"]
StageShape = Literal["proscenium", "thrust", "arena_center", "runway", "custom_polygon"]


class VenueBase(BaseModel):
    name: str = Field(..., min_length=1, max_length=255)
    notes: str = ""
    venue_width_cm: float = Field(0.0, ge=0)
    venue_height_cm: float = Field(0.0, ge=0)
    stage_x_cm: float = Field(0.0, ge=0)
    stage_y_cm: float = Field(0.0, ge=0)
    stage_width_cm: float = Field(0.0, ge=0)
    stage_height_cm: float = Field(0.0, ge=0)
    footprint_shape: FootprintShape = "rectangular"
    stage_shape: StageShape = "proscenium"
    background_image_url: str = Field("", max_length=1024)
    audience_polygon: list[list[float]] = Field(default_factory=list)
    # Custom footprints/stages are drawn as polygons (venue cm for the footprint,
    # stage-relative cm for the stage) when the matching *_shape is "custom_polygon".
    footprint_polygon: list[list[float]] = Field(default_factory=list)
    stage_polygon: list[list[float]] = Field(default_factory=list)

    @field_validator("audience_polygon")
    @classmethod
    def _check_audience_polygon(cls, value):
        return check_polygon(value)

    @field_validator("footprint_polygon", "stage_polygon")
    @classmethod
    def _check_custom_polygons(cls, value):
        return check_polygon(value)


class VenueCreate(VenueBase):
    pass


class VenueUpdate(BaseModel):
    name: str | None = Field(None, min_length=1, max_length=255)
    notes: str | None = None
    venue_width_cm: float | None = Field(None, ge=0)
    venue_height_cm: float | None = Field(None, ge=0)
    stage_x_cm: float | None = Field(None, ge=0)
    stage_y_cm: float | None = Field(None, ge=0)
    stage_width_cm: float | None = Field(None, ge=0)
    stage_height_cm: float | None = Field(None, ge=0)
    footprint_shape: FootprintShape | None = None
    stage_shape: StageShape | None = None
    background_image_url: str | None = Field(None, max_length=1024)
    audience_polygon: list[list[float]] | None = None
    footprint_polygon: list[list[float]] | None = None
    stage_polygon: list[list[float]] | None = None

    @field_validator("audience_polygon")
    @classmethod
    def _check_audience_polygon(cls, value):
        return check_polygon(value)

    @field_validator("footprint_polygon", "stage_polygon")
    @classmethod
    def _check_custom_polygons(cls, value):
        return check_polygon(value)


class VenueRead(VenueBase):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    propagated_at: datetime | None = None
    created_at: datetime
    updated_at: datetime


class JobVenueAssign(BaseModel):
    venue_id: UUID | None = None


class VenuePropagate(BaseModel):
    scope: Literal["all", "newer"]


class VenuePropagateResult(BaseModel):
    updated: int


class VenuePowerGroupBase(BaseModel):
    name: str = ""
    rating_amps: float | None = Field(None, gt=0)
    phases: int = Field(1, ge=1, le=3)
    phase: Literal["L1", "L2", "L3"] | None = None
    notes: str = ""
    # kind classifies the node in the supply tree: 'incoming' (mains) | 'panel' (board) |
    # 'group' (fused circuit inside a panel that outlets plug into). Kept in sync with is_incoming.
    kind: Literal["incoming", "panel", "group"] = "group"
    # parent_id nests a panel under another panel (or the incoming supply); null = top level.
    # For a 'group' the parent is the panel it belongs to.
    parent_id: UUID | None = None
    # True for the single supply the venue draws from (its load is the sum of every outlet).
    is_incoming: bool = False


class VenuePowerGroupCreate(VenuePowerGroupBase):
    pass


class VenuePowerGroupUpdate(BaseModel):
    name: str | None = None
    rating_amps: float | None = Field(None, gt=0)
    phases: int | None = Field(None, ge=1, le=3)
    phase: Literal["L1", "L2", "L3"] | None = None
    notes: str | None = None
    kind: Literal["incoming", "panel", "group"] | None = None
    parent_id: UUID | None = None
    is_incoming: bool | None = None


class VenuePowerGroupRead(VenuePowerGroupBase):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    venue_id: UUID


class VenuePowerOutletBase(BaseModel):
    name: str = ""
    connector: str = ""
    rating_amps: float | None = None
    group_id: UUID | None = None
    x_cm: float | None = None
    y_cm: float | None = None
    notes: str = ""


class VenuePowerOutletCreate(VenuePowerOutletBase):
    pass


class VenuePowerOutletUpdate(BaseModel):
    name: str | None = None
    connector: str | None = None
    rating_amps: float | None = None
    group_id: UUID | None = None
    x_cm: float | None = None
    y_cm: float | None = None
    notes: str | None = None


class VenuePowerOutletRead(VenuePowerOutletBase):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    venue_id: UUID


class VenuePowerElementLoad(BaseModel):
    """The load drawn through one supply element (outlet or group) and whether it is over limit."""

    id: UUID
    watts: float
    amps: float
    over: bool


class VenuePowerLoadRead(BaseModel):
    """Device-driven load for a venue's power supply, computed server-side and shared by the venue
    Standard Base Rig and the job workspace so both show the same over-limit check."""

    outlets: list[VenuePowerElementLoad] = Field(default_factory=list)
    groups: list[VenuePowerElementLoad] = Field(default_factory=list)
    incoming: VenuePowerElementLoad | None = None
    total_watts: float = 0.0
    total_amps: float = 0.0


# --- Standard Base Rig -------------------------------------------------------------------------
# A venue's Standard Base Rig is a graph (devices + connection edges) owned by the venue rather
# than by a job. It is stored in the same unified `graph_*` tables and cloned onto a job when the
# venue is assigned. The write schemas mirror the job graph's device/edge shapes so the same
# editor can drive both; the client keeps device/edge ids stable across a GET -> edit -> PUT round
# trip, which avoids any id remapping on the server.


class VenueBaseRigDeviceWrite(BaseModel):
    id: UUID
    domain: Domain
    kind: str = ""
    name: str
    notes: str = ""
    position: int = 0
    attributes: dict = Field(default_factory=dict)
    ports: list[Port] = Field(default_factory=list)
    canvas_x_cm: float | None = None
    canvas_y_cm: float | None = None
    canvas_rotation: float = 0.0
    case_parent_id: UUID | None = None
    stockwire_product_id: str | None = None
    stockwire_product_name: str | None = None
    stockwire_device_id: str | None = None
    stockwire_booked: bool | None = None


class VenueBaseRigEdgeWrite(BaseModel):
    id: UUID
    signal: Signal
    src_device_id: UUID
    src_port: str
    dst_device_id: UUID
    dst_port: str
    channels: int = 1
    phase: Literal["L1", "L2", "L3"] | None = None
    cable_label: str = ""
    notes: str = ""
    attributes: dict = Field(default_factory=dict)


class VenueBaseRigWrite(BaseModel):
    devices: list[VenueBaseRigDeviceWrite] = Field(default_factory=list)
    edges: list[VenueBaseRigEdgeWrite] = Field(default_factory=list)
