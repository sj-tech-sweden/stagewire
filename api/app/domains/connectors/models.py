import uuid
from datetime import datetime

from sqlalchemy import Boolean, DateTime, Integer, String, Uuid
from sqlalchemy.orm import Mapped, mapped_column

from app.core.db import Base


class ConnectorKind(Base):
    """A connector type added by the users on top of the built-in presets.

    The built-in presets live in the web app (``CONNECTOR_CHOICES``). These rows are the shared,
    global extension of that list: every connector field in every job offers them. ``key`` is the
    value stored on ports and patch points (lowercase, no spaces) and ``label`` is what people see.
    """

    __tablename__ = "connector_kinds"

    id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4)
    key: Mapped[str] = mapped_column(String(64), unique=True, index=True, nullable=False)
    label: Mapped[str] = mapped_column(String(128), nullable=False)
    # A power connector also carries what the power tree needs: amps per phase (0 = installation
    # wiring that is rated by hand), 1 or 3 phases and circuits. Plain kinds leave these empty.
    power: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    amps: Mapped[int | None] = mapped_column(Integer, nullable=True)
    phases: Mapped[int | None] = mapped_column(Integer, nullable=True)
    circuits: Mapped[int | None] = mapped_column(Integer, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now()
    )
