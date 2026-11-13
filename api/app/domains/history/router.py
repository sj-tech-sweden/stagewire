"""History endpoints for jobs and venues: list versions, undo, redo, restore."""

from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.db import get_db
from app.domains.audio.models import ProductionJob
from app.domains.audio.ws import publish_job_event, publish_venue_event
from app.domains.auth.deps import get_current_user
from app.domains.auth.models import User
from app.domains.history import service
from app.domains.venues.models import Venue

router = APIRouter(dependencies=[Depends(get_current_user)], tags=["history"])


class RestoreBody(BaseModel):
    seq: int = Field(ge=0)


async def _require(db: AsyncSession, kind: str, scope_id: uuid.UUID) -> None:
    model = ProductionJob if kind == "job" else Venue
    if await db.get(model, scope_id) is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, f"{kind.title()} not found")


async def _state(db: AsyncSession, kind: str, scope_id: uuid.UUID, limit: int = 100) -> dict:
    rows = await service.entries(db, kind, scope_id)
    cursor = service.cursor_of(rows)
    names: dict[int, str] = {}
    actor_ids = {e.actor_id for e in rows if e.actor_id}
    if actor_ids:
        for user in await db.scalars(select(User).where(User.id.in_(actor_ids))):
            names[user.id] = user.full_name or user.email
    return {
        "cursor": cursor,
        "can_undo": any(not e.undone for e in rows),
        "can_redo": any(e.undone for e in rows),
        "entries": [
            {
                "seq": e.seq,
                "label": e.label,
                # stable key for translating the step name on the client ("Update channel" ->
                # "update_channel"); the label is the untranslated fallback
                "action": e.label.lower().replace(" ", "_"),
                "summary": e.summary,
                "actor": names.get(e.actor_id) if e.actor_id else None,
                "created_at": e.created_at.isoformat() if e.created_at else None,
                "undone": e.undone,
                "changes": e.change_count,
            }
            for e in rows[:limit]
        ],
    }


async def _announce(kind: str, scope_id: uuid.UUID, state: dict) -> None:
    """Tell every open workspace to reload: a restore can touch any number of rows."""
    publish = publish_job_event if kind == "job" else publish_venue_event
    await publish(scope_id, "history.restore", {"cursor": state["cursor"]})


def _register(prefix: str, kind: str) -> None:
    @router.get(f"{prefix}/history", name=f"list_{kind}_history")
    async def list_history(
        scope_id: uuid.UUID,
        limit: int = Query(100, ge=1, le=500),
        db: AsyncSession = Depends(get_db),
    ) -> dict:
        await _require(db, kind, scope_id)
        return await _state(db, kind, scope_id, limit)

    async def move(scope_id: uuid.UUID, undo: bool, force: bool, db: AsyncSession) -> dict:
        await _require(db, kind, scope_id)
        entry = await service.step(db, kind, scope_id, undo=undo, force=force)
        if entry is None:
            raise HTTPException(
                status.HTTP_409_CONFLICT, "Nothing to undo" if undo else "Nothing to redo"
            )
        state = await _state(db, kind, scope_id)
        await _announce(kind, scope_id, state)
        return {**state, "applied": {"seq": entry.seq, "label": entry.label}}

    @router.post(f"{prefix}/history/undo", name=f"undo_{kind}")
    async def undo(
        scope_id: uuid.UUID, force: bool = False, db: AsyncSession = Depends(get_db)
    ) -> dict:
        return await move(scope_id, True, force, db)

    @router.post(f"{prefix}/history/redo", name=f"redo_{kind}")
    async def redo(
        scope_id: uuid.UUID, force: bool = False, db: AsyncSession = Depends(get_db)
    ) -> dict:
        return await move(scope_id, False, force, db)

    @router.post(f"{prefix}/history/restore", name=f"restore_{kind}")
    async def restore(
        scope_id: uuid.UUID,
        payload: RestoreBody,
        force: bool = False,
        db: AsyncSession = Depends(get_db),
    ) -> dict:
        await _require(db, kind, scope_id)
        steps = await service.restore(db, kind, scope_id, payload.seq, force=force)
        state = await _state(db, kind, scope_id)
        await _announce(kind, scope_id, state)
        return {**state, "steps": steps}


_register("/jobs/{scope_id}", "job")
_register("/venues/{scope_id}", "venue")
