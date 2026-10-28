from datetime import datetime
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.domains.audio.polygon import check_polygon


class VenueBase(BaseModel):
    name: str = Field(..., min_length=1, max_length=255)
    notes: str = ""
    venue_width_cm: float = Field(0.0, ge=0)
    venue_height_cm: float = Field(0.0, ge=0)
    stage_x_cm: float = Field(0.0, ge=0)
    stage_y_cm: float = Field(0.0, ge=0)
    stage_width_cm: float = Field(0.0, ge=0)
    stage_height_cm: float = Field(0.0, ge=0)
    background_image_url: str = Field("", max_length=1024)
    audience_polygon: list[list[float]] = Field(default_factory=list)

    @field_validator("audience_polygon")
    @classmethod
    def _check_audience_polygon(cls, value):
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
    background_image_url: str | None = Field(None, max_length=1024)
    audience_polygon: list[list[float]] | None = None

    @field_validator("audience_polygon")
    @classmethod
    def _check_audience_polygon(cls, value):
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


class VenuePowerOutletBase(BaseModel):
    name: str = ""
    connector: str = ""
    x_cm: float | None = None
    y_cm: float | None = None
    notes: str = ""


class VenuePowerOutletCreate(VenuePowerOutletBase):
    pass


class VenuePowerOutletUpdate(BaseModel):
    name: str | None = None
    connector: str | None = None
    x_cm: float | None = None
    y_cm: float | None = None
    notes: str | None = None


class VenuePowerOutletRead(VenuePowerOutletBase):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    venue_id: UUID
