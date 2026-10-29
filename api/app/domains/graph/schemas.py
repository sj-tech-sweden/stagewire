from datetime import datetime
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

Domain = Literal["audio", "lighting", "video", "power", "rigging", "other"]
Signal = Literal["audio", "video", "dmx", "power", "data"]


class Port(BaseModel):
    id: str = Field(min_length=1, max_length=64)
    direction: Literal["in", "out"]
    signal: Signal | None = None
    connector: str | None = None
    channels: int | None = Field(default=None, ge=1)
    max_connections: int | None = Field(default=None, ge=1)
    label: str = ""


class GraphDeviceBase(BaseModel):
    domain: Domain
    kind: str = Field(default="", max_length=64)
    name: str = Field(min_length=1, max_length=255)
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


class GraphDeviceCreate(GraphDeviceBase):
    pass


class GraphDeviceUpdate(BaseModel):
    domain: Domain | None = None
    kind: str | None = Field(default=None, max_length=64)
    name: str | None = Field(default=None, min_length=1, max_length=255)
    notes: str | None = None
    position: int | None = None
    attributes: dict | None = None
    ports: list[Port] | None = None
    canvas_x_cm: float | None = None
    canvas_y_cm: float | None = None
    canvas_rotation: float | None = None
    case_parent_id: UUID | None = None
    stockwire_product_id: str | None = None
    stockwire_product_name: str | None = None
    stockwire_device_id: str | None = None
    stockwire_booked: bool | None = None
    expected_revision: int = Field(ge=1)


class GraphDeviceRead(GraphDeviceBase):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    job_id: UUID
    stockwire_request_status: str | None = None
    created_at: datetime
    revision: int


class ConnectionEdgeBase(BaseModel):
    signal: Signal
    src_device_id: UUID
    src_port: str
    dst_device_id: UUID
    dst_port: str
    channels: int = Field(default=1, ge=1)
    phase: Literal["L1", "L2", "L3"] | None = None
    cable_label: str = ""
    notes: str = ""
    attributes: dict = Field(default_factory=dict)


class ConnectionEdgeCreate(ConnectionEdgeBase):
    pass


class ConnectionEdgeUpdate(BaseModel):
    channels: int | None = Field(default=None, ge=1)
    phase: Literal["L1", "L2", "L3"] | None = None
    cable_label: str | None = None
    notes: str | None = None
    attributes: dict | None = None
    expected_revision: int = Field(ge=1)


class ConnectionEdgeRead(ConnectionEdgeBase):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    job_id: UUID
    revision: int


class GraphRead(BaseModel):
    devices: list[GraphDeviceRead]
    edges: list[ConnectionEdgeRead]


class IssueRead(BaseModel):
    code: str
    message: str
    edge_id: str | None = None
    device_id: str | None = None


class HopRead(BaseModel):
    depth: int
    device_id: str
    edge: ConnectionEdgeRead


class TraceRead(BaseModel):
    root: str
    direction: Literal["upstream", "downstream"]
    hops: list[HopRead]
    truncated: bool = False
    issues: list[IssueRead] = []


class PhaseLoadRead(BaseModel):
    L1: float
    L2: float
    L3: float
    imbalance_pct: float
