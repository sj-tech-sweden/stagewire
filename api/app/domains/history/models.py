import uuid
from datetime import datetime

from sqlalchemy import JSON, Boolean, DateTime, Integer, String, UniqueConstraint, Uuid
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.core.db import Base

JsonType = JSON().with_variant(JSONB(), "postgresql")


class HistoryEntry(Base):
    """One undoable step: every tracked row change one write request made, in one scope.

    A *scope* is a job or a venue (``scope_kind`` + ``scope_id``); each has its own linear
    history, so undoing in one job never touches another. ``changes`` is the row-level diff
    (see ``recorder.Change``): enough to restore the exact state before (undo) or after (redo).
    ``scope_id`` is deliberately not a foreign key because it points at either of two tables.
    """

    __tablename__ = "history_entries"
    __table_args__ = (
        UniqueConstraint("scope_kind", "scope_id", "seq", name="uq_history_scope_seq"),
    )

    id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4)
    scope_kind: Mapped[str] = mapped_column(String(8), nullable=False, index=True)
    scope_id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), nullable=False, index=True)
    seq: Mapped[int] = mapped_column(Integer, nullable=False)
    label: Mapped[str] = mapped_column(String(255), default="", nullable=False)
    summary: Mapped[str] = mapped_column(String(255), default="", nullable=False)
    actor_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    changes: Mapped[list] = mapped_column(JsonType, default=list, nullable=False)
    # Stored next to ``changes`` so the version list never has to load the (large) diffs.
    change_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    # An undone entry stays in the list (it is the redo stack) until a new change replaces it.
    undone: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now()
    )
