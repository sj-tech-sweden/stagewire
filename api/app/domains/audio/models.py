import uuid
from datetime import date, datetime

from sqlalchemy import (
    JSON,
    Boolean,
    Date,
    DateTime,
    Float,
    ForeignKey,
    Integer,
    String,
    Text,
    UniqueConstraint,
    Uuid,
    false,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.core.db import Base


class ProductionJob(Base):
    __tablename__ = "production_jobs"

    id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4)
    stockwire_job_id: Mapped[str | None] = mapped_column(String(255), nullable=True, index=True)
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    venue_name: Mapped[str] = mapped_column(String(255), default="")
    event_date: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    # Inclusive rental date range used for Stockwire availability checks. Stored as plain
    # dates (not datetimes) because the Stockwire availability endpoint takes $date bounds.
    start_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    end_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    notes: Mapped[str] = mapped_column(Text, default="", nullable=False)
    stage_width_cm: Mapped[float] = mapped_column(Float, default=0.0)
    stage_height_cm: Mapped[float] = mapped_column(Float, default=0.0)
    venue_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("venues.id", ondelete="SET NULL"), nullable=True, index=True
    )
    venue_width_cm: Mapped[float] = mapped_column(Float, default=0.0)
    venue_height_cm: Mapped[float] = mapped_column(Float, default=0.0)
    stage_x_cm: Mapped[float] = mapped_column(Float, default=0.0)
    stage_y_cm: Mapped[float] = mapped_column(Float, default=0.0)
    venue_background_image_url: Mapped[str] = mapped_column(String(1024), default="")
    venue_footprint_shape: Mapped[str] = mapped_column(
        String(32), default="rectangular", nullable=False
    )
    venue_stage_shape: Mapped[str] = mapped_column(String(32), default="proscenium", nullable=False)
    audience_polygon: Mapped[list] = mapped_column(JSON, default=list)
    venue_footprint_polygon: Mapped[list] = mapped_column(JSON, default=list, nullable=False)
    venue_stage_polygon: Mapped[list] = mapped_column(JSON, default=list, nullable=False)
    cable_plan: Mapped[dict] = mapped_column(JSON, default=dict)
    # Per-job NetBox integration toggle. The global integration must also be
    # enabled; this lets individual jobs opt out (or in) of device mirroring and
    # IP assignment even when NetBox is configured globally.
    netbox_enabled: Mapped[bool] = mapped_column(
        Boolean, default=False, nullable=False, server_default=false()
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now()
    )


class StockwireRequirementLink(Base):
    """Maps a Stagewire-created rental requirement back to the thing that created it.

    ``source`` is the provenance the sync uses to decide what it may delete:

    * ``sync`` — a product-level requirement created by ``sync_job_to_stockwire``.
      These are the only requirements the sync is allowed to remove, and only
      when the Stagewire gear behind them is gone.
    * ``request`` — a requirement created by the explicit "request to add" flow.
      It is recorded so it is never mistaken for sync-owned, but it is a request
      to the rental company, not a mirror of the plot, so the sync leaves it be.

    Requirements a human added in the rental job have no link row at all and are
    therefore never touched by either path. Never delete a requirement by product
    match: two people can need the same product for different reasons.
    """

    __tablename__ = "stockwire_requirement_links"
    __table_args__ = (UniqueConstraint("job_id", "item_key", name="uq_stockwire_link_job_item"),)

    id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4)
    job_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("production_jobs.id", ondelete="CASCADE"), nullable=True, index=True
    )
    venue_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("venues.id", ondelete="CASCADE"), nullable=True, index=True
    )
    item_key: Mapped[str] = mapped_column(String(255), nullable=False)
    product_id: Mapped[str] = mapped_column(String(64), nullable=False)
    product_name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    rental_requirement_id: Mapped[int] = mapped_column(Integer, nullable=False)
    quantity: Mapped[int] = mapped_column(Integer, nullable=False, default=1, server_default="1")
    source: Mapped[str] = mapped_column(
        String(32), nullable=False, default="sync", server_default="sync"
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now()
    )


class WwbShowFile(Base):
    """The Shure Wireless Workbench ``.shw`` show file imported for a channel list.

    Kept so the same file can be re-exported with Stagewire's coordinated frequencies
    written back into it (round-tripping through WWB). Keyed one-to-one by the channel
    list's graph node id.
    """

    __tablename__ = "wwb_show_files"

    list_node_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("graph_devices.id", ondelete="CASCADE"), primary_key=True
    )
    # Owned by exactly one context: a job or a venue. A venue's Standard Base Rig keeps its
    # own .shw files, so the storage row is scoped the same way as the lighting library.
    job_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("production_jobs.id", ondelete="CASCADE"), nullable=True, index=True
    )
    venue_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("venues.id", ondelete="CASCADE"), nullable=True, index=True
    )
    filename: Mapped[str] = mapped_column(String(255), default="", nullable=False)
    content: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now()
    )
