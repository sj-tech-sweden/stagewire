import uuid
from datetime import datetime

from sqlalchemy import JSON, Boolean, DateTime, Float, ForeignKey, Integer, String, Text, Uuid
from sqlalchemy.orm import Mapped, mapped_column

from app.core.db import Base


class Venue(Base):
    """A reusable venue template (shared across all users).

    Jobs copy these dimensions when a venue is assigned, so editing a venue only
    changes other jobs when it is explicitly propagated.
    """

    __tablename__ = "venues"

    id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    notes: Mapped[str] = mapped_column(Text, default="", nullable=False)
    venue_width_cm: Mapped[float] = mapped_column(Float, default=0.0)
    venue_height_cm: Mapped[float] = mapped_column(Float, default=0.0)
    stage_x_cm: Mapped[float] = mapped_column(Float, default=0.0)
    stage_y_cm: Mapped[float] = mapped_column(Float, default=0.0)
    stage_width_cm: Mapped[float] = mapped_column(Float, default=0.0)
    stage_height_cm: Mapped[float] = mapped_column(Float, default=0.0)
    footprint_shape: Mapped[str] = mapped_column(String(32), default="rectangular", nullable=False)
    stage_shape: Mapped[str] = mapped_column(String(32), default="proscenium", nullable=False)
    background_image_url: Mapped[str] = mapped_column(String(1024), default="", nullable=False)
    audience_polygon: Mapped[list] = mapped_column(JSON, default=list, nullable=False)
    footprint_polygon: Mapped[list] = mapped_column(JSON, default=list, nullable=False)
    stage_polygon: Mapped[list] = mapped_column(JSON, default=list, nullable=False)
    # Cable raceways and routing settings for the venue's Standard Base Rig, stored the same way as
    # a job's cable_plan (a `cableways` array plus routing `settings`). Jobs clone the venue's
    # cableways as a starting point and add their own runs on top, so the venue defines the fixed
    # infrastructure (trays, conduits) and each job extends it.
    cable_plan: Mapped[dict] = mapped_column(JSON, default=dict, nullable=False)
    propagated_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(), onupdate=lambda: datetime.now()
    )


class VenuePowerGroup(Base):
    """A node in the venue's power supply tree.

    The tree has five kinds, which together model how a real installation (and its temporary
    extensions) are wired:

    - ``incoming``: the mains — a supply root with no parent. Its load is the whole subtree.
    - ``generator``: a temporary second supply root (hired when the venue power is not enough). No
      parent; its load is computed independently so the per-source over-limit check compares mains
      against generator.
    - ``panel``: a permanent distribution board. It hangs off a supply root or another board and
      *contains* circuits. It carries the board's main breaker rating.
    - ``breakout``: a temporary distro box (the kind you hire). Wired like a panel but flagged
      ``temporary``; it also *contains* circuits.
    - ``group``: a fused circuit inside a panel/breakout. Outlets connect to groups (not to boards),
      and the group's rating is the fuse/breaker for everything on its outlets.

    ``is_incoming`` mirrors ``kind == 'incoming'`` so existing callers can keep spotting the mains
    supply root. ``temporary`` flags hired equipment (generators, breakouts, cables) that is not
    part of the venue's permanent install. ``parent_id`` is self-referential and set NULL if the
    parent is removed (a detached board becomes top-level).
    """

    __tablename__ = "venue_power_groups"

    id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4)
    venue_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("venues.id", ondelete="CASCADE"), index=True
    )
    name: Mapped[str] = mapped_column(String(255), default="")
    rating_amps: Mapped[float | None] = mapped_column(Float, nullable=True)
    phases: Mapped[int] = mapped_column(Integer, default=1, nullable=False)
    # Which phase a one-phase group is on (L1 when not set); a three-phase group spreads its load.
    phase: Mapped[str | None] = mapped_column(String(2), nullable=True)
    notes: Mapped[str] = mapped_column(Text, default="")
    # What this node is in the supply tree (see class docstring): 'incoming' (mains) | 'generator'
    # (temporary supply) | 'panel' (permanent board) | 'breakout' (temporary distro) | 'group'
    # (fused circuit). kind drives both the icon in the UI and which parents are allowed.
    kind: Mapped[str] = mapped_column(String(16), default="group", nullable=False, index=True)
    # Temporary equipment (a hired generator, a breakout distro, etc.) is drawn distinctly and is
    # not part of the venue's permanent install. Most useful on generators/breakouts.
    temporary: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    # The power tree is nested: a board may hang under the incoming supply, a generator, another
    # board, or a breakout. parent_id is self-referential and set NULL if the parent is removed.
    parent_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("venue_power_groups.id", ondelete="SET NULL"), nullable=True, index=True
    )
    is_incoming: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)


class VenuePowerOutlet(Base):
    """A mains outlet that belongs to a venue, and where it sits on the stage plot (cm)."""

    __tablename__ = "venue_power_outlets"

    id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4)
    venue_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("venues.id", ondelete="CASCADE"), index=True
    )
    name: Mapped[str] = mapped_column(String(255), default="")
    connector: Mapped[str] = mapped_column(String(64), default="")
    rating_amps: Mapped[float | None] = mapped_column(Float, nullable=True)
    group_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("venue_power_groups.id", ondelete="SET NULL"), nullable=True, index=True
    )
    x_cm: Mapped[float | None] = mapped_column(Float, nullable=True)
    y_cm: Mapped[float | None] = mapped_column(Float, nullable=True)
    notes: Mapped[str] = mapped_column(Text, default="")
