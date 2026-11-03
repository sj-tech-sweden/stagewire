"""Persistence for imported Wireless Workbench ``.shw`` show files.

A channel list keeps the last ``.shw`` it imported so it can be re-exported with
Stagewire's coordinated frequencies written back into the same file (round-tripping
through WWB). The raw XML is stored verbatim; the exporter mutates it in place.
"""

import uuid

from sqlalchemy.ext.asyncio import AsyncSession

from app.domains.audio.models import WwbShowFile


async def get_show_file(db: AsyncSession, list_node_id: uuid.UUID) -> str | None:
    """Return the stored ``.shw`` XML for a channel list, or ``None`` if none."""
    row = await db.get(WwbShowFile, list_node_id)
    return row.content if row is not None else None


async def upsert_show_file(
    db: AsyncSession,
    list_node_id: uuid.UUID,
    job_id: uuid.UUID,
    content: str,
    filename: str,
) -> None:
    """Store (or replace) the ``.shw`` XML for a channel list. Caller commits."""
    existing = await db.get(WwbShowFile, list_node_id)
    if existing is not None:
        existing.content = content
        existing.filename = filename
        existing.job_id = job_id
    else:
        db.add(
            WwbShowFile(
                list_node_id=list_node_id,
                job_id=job_id,
                content=content,
                filename=filename,
            )
        )
