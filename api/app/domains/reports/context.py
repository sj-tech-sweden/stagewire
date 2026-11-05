"""The context discriminator that lets a venue emit the same reports a job can.

Every job-domain report is built from a graph (and, for power, a supply tree) that a venue's
Standard Base Rig already owns. ``JobOrVenue`` is the single value the design doc prescribes
(§5): instead of threading a bare ``job_id`` through the report builders, they take a context
that is either a job or a venue, and resolve the right rows via :func:`scope_filter`.

A venue has no ``ProductionJob`` row, so :func:`load_subject` returns a lightweight namespace
that exposes the job-shaped attributes the report templates read (``title``, ``venue_name``,
``stage_width_cm`` …) sourced from the ``venues`` table. That keeps the templates untouched.
"""

from dataclasses import dataclass
from types import SimpleNamespace
from typing import Literal
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.domains.audio.models import ProductionJob
from app.domains.graph.models import scope_filter
from app.domains.venues.models import Venue


@dataclass(frozen=True)
class JobOrVenue:
    """Exactly one of a job or a venue — the owner of a report's source graph."""

    scope: Literal["job", "venue"]
    id: UUID

    @property
    def is_job(self) -> bool:
        return self.scope == "job"

    @property
    def is_venue(self) -> bool:
        return self.scope == "venue"

    @classmethod
    def job(cls, id: UUID) -> "JobOrVenue":
        return cls("job", id)

    @classmethod
    def venue(cls, id: UUID) -> "JobOrVenue":
        return cls("venue", id)

    def filter(self, model):
        """The SQLAlchemy predicate narrowing ``model`` rows to this context."""
        return scope_filter(
            model,
            job_id=self.id if self.is_job else None,
            venue_id=self.id if self.is_venue else None,
        )

    def as_kwargs(self) -> dict:
        """Expand to ``job_id=`` / ``venue_id=`` for the lighting-style native helpers."""
        return {"job_id": self.id} if self.is_job else {"venue_id": self.id}


def _venue_subject(venue: Venue) -> SimpleNamespace:
    """A job-shaped view of a venue, so report templates need no venue branch.

    ``title`` / ``venue_name`` both map to the venue name; ``event_date`` is meaningless for a
    template venue and is left blank. Stage geometry comes from the venue's own stage fields, and
    the audience polygon / cable plan fall back to the venue equivalents (a venue has no routed
    cable plan, so it is empty and the stage-plot report draws no cables).
    """
    return SimpleNamespace(
        id=venue.id,
        title=venue.name,
        venue_name=venue.name,
        event_date=None,
        notes=venue.notes or "",
        venue_width_cm=venue.venue_width_cm or 0.0,
        venue_height_cm=venue.venue_height_cm or 0.0,
        stage_width_cm=venue.stage_width_cm or 0.0,
        stage_height_cm=venue.stage_height_cm or 0.0,
        stage_x_cm=venue.stage_x_cm or 0.0,
        stage_y_cm=venue.stage_y_cm or 0.0,
        audience_polygon=list(venue.audience_polygon or []),
        cable_plan={},
    )


async def load_subject(db: AsyncSession, context: JobOrVenue) -> SimpleNamespace:
    """The job-shaped object a report template titles itself with.

    For a job this is the ``ProductionJob``; for a venue it is :func:`_venue_subject`. Raises
    ``LookupError`` when the context entity does not exist, matching ``_load_job``.
    """
    if context.is_job:
        job = (
            (await db.execute(select(ProductionJob).where(ProductionJob.id == context.id)))
            .scalars()
            .first()
        )
        if job is None:
            raise LookupError("Production job not found")
        return job
    venue = await db.get(Venue, context.id)
    if venue is None:
        raise LookupError("Venue not found")
    return _venue_subject(venue)
