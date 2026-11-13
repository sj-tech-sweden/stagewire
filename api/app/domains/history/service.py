"""Undo, redo and restore: apply the recorded row diffs backwards or forwards.

Each scope (job or venue) has one linear history ordered by ``seq``. The *cursor* is the highest
``seq`` that is not undone; entries above it are the redo stack. A new change after an undo drops
the redo stack (the usual editor behaviour). Restoring "to a version" means undoing or redoing
entry by entry until the cursor sits on that ``seq``.

An undo applies the exact inverse of what the request did, so it needs no knowledge of the
request: rows the request inserted are deleted, rows it deleted are re-inserted from the stored old
values, and changed columns go back to their old values. Before touching a row the current values
are compared with what the entry recorded; if someone changed it since (outside the tracked flow)
the step is refused with the conflicting rows unless ``force`` is given.
"""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from fastapi import HTTPException, status
from sqlalchemy import delete, func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core import db as db_mod
from app.domains.audio.models import ProductionJob
from app.domains.graph.models import ConnectionEdge, GraphDevice
from app.domains.history import recorder
from app.domains.history.models import HistoryEntry
from app.domains.venues.models import Venue, VenuePowerGroup, VenuePowerOutlet

MODELS: dict[str, type] = {
    "graph_devices": GraphDevice,
    "graph_connection_edges": ConnectionEdge,
    "production_jobs": ProductionJob,
    "venues": Venue,
    "venue_power_groups": VenuePowerGroup,
    "venue_power_outlets": VenuePowerOutlet,
}
# Re-inserts must put devices before the edges that reference them; deletes go the other way.
INSERT_ORDER = [
    "production_jobs",
    "venues",
    "venue_power_groups",
    "venue_power_outlets",
    "graph_devices",
    "graph_connection_edges",
]
KEEP = 500  # entries kept per scope; older ones are pruned when a new one is recorded


def humanize(name: str) -> str:
    text = (name or "change").replace("_", " ").strip()
    return text[:1].upper() + text[1:]


async def record(rec: recorder.Recorder, actor_id: int | None, label: str) -> None:
    """Store a finished request's changes: one entry per scope, in its own transaction.

    Two requests finishing together can pick the same next ``seq``; the unique constraint rejects
    the second, which then simply retries with the new maximum, so no write goes unrecorded.
    """
    for attempt in range(4):
        try:
            await _record_once(rec, actor_id, label)
            return
        except IntegrityError:
            if attempt == 3:
                raise


async def _record_once(rec: recorder.Recorder, actor_id: int | None, label: str) -> None:
    by_scope: dict[tuple[str, str], list[recorder.Change]] = {}
    for change in rec.result():
        by_scope.setdefault(change.scope, []).append(change)
    if not by_scope:
        return
    async with db_mod.SessionLocal() as db:
        for (kind, scope_id), changes in by_scope.items():
            sid = uuid.UUID(scope_id)
            # a new change ends the redo stack
            await db.execute(
                delete(HistoryEntry).where(
                    HistoryEntry.scope_kind == kind,
                    HistoryEntry.scope_id == sid,
                    HistoryEntry.undone.is_(True),
                )
            )
            top = await db.scalar(
                select(func.max(HistoryEntry.seq)).where(
                    HistoryEntry.scope_kind == kind, HistoryEntry.scope_id == sid
                )
            )
            names = list(dict.fromkeys(c.name for c in changes if c.name))
            summary = ", ".join(names[:3]) + (f" +{len(names) - 3}" if len(names) > 3 else "")
            db.add(
                HistoryEntry(
                    scope_kind=kind,
                    scope_id=sid,
                    seq=(top or 0) + 1,
                    label=label,
                    summary=summary[:255],
                    actor_id=actor_id,
                    changes=[c.as_json() for c in changes],
                    change_count=len(changes),
                )
            )
            # keep the table bounded: drop entries far behind the newest
            old = (top or 0) + 1 - KEEP
            if old > 0:
                await db.execute(
                    delete(HistoryEntry).where(
                        HistoryEntry.scope_kind == kind,
                        HistoryEntry.scope_id == sid,
                        HistoryEntry.seq <= old,
                    )
                )
        await db.commit()


_LIGHT = (
    HistoryEntry.id,
    HistoryEntry.seq,
    HistoryEntry.label,
    HistoryEntry.summary,
    HistoryEntry.actor_id,
    HistoryEntry.undone,
    HistoryEntry.created_at,
    HistoryEntry.change_count,
)


async def purge(db: AsyncSession, kind: str, scope_id: uuid.UUID) -> None:
    """Drop a job's or venue's whole history (called when the job / venue itself is deleted).

    ``scope_id`` is not a foreign key (it points at either table), so nothing cascades; without
    this the diffs, which hold full row snapshots, would stay behind forever.
    """
    await db.execute(
        delete(HistoryEntry).where(
            HistoryEntry.scope_kind == kind, HistoryEntry.scope_id == scope_id
        )
    )


async def entries(db: AsyncSession, kind: str, scope_id: uuid.UUID, limit: int | None = None):
    """Version list rows, newest first, *without* the diffs (they can be large)."""
    query = (
        select(*_LIGHT)
        .where(HistoryEntry.scope_kind == kind, HistoryEntry.scope_id == scope_id)
        .order_by(HistoryEntry.seq.desc())
    )
    if limit:
        query = query.limit(limit)
    return list((await db.execute(query)).all())


def cursor_of(rows: list) -> int:
    return max((e.seq for e in rows if not e.undone), default=0)


def _pk_value(model: type, raw: str) -> Any:
    column = model.__table__.primary_key.columns.values()[0]
    return recorder.from_json(column, raw)


def _apply_values(obj: Any, values: dict) -> None:
    table = type(obj).__table__
    for key, value in values.items():
        if key in table.columns:
            setattr(obj, key, recorder.from_json(table.columns[key], value))


async def _current(db: AsyncSession, change: dict) -> Any:
    return await db.get(MODELS[change["table"]], _pk_value(MODELS[change["table"]], change["pk"]))


def _differs(obj: Any, expected: dict) -> bool:
    """Whether the row's current values differ from what the entry recorded.

    Timestamps are not compared: a naive local time written by the app comes back timezone-aware
    from PostgreSQL, so the same instant would never compare equal. They carry no user data.
    """
    table = type(obj).__table__
    for key, value in expected.items():
        column = table.columns.get(key)
        if column is None:
            continue
        try:
            if column.type.python_type is datetime:
                continue
        except NotImplementedError:
            pass
        if recorder.to_json(getattr(obj, key, None)) != value:
            return True
    return False


async def _apply(db: AsyncSession, changes: list[dict], *, forward: bool, force: bool) -> None:
    """Apply a diff list forwards (redo) or as its inverse (undo); raises 409 on conflicts."""
    conflicts: list[str] = []
    # what we remove / re-create is ordered by table dependencies (see INSERT_ORDER)
    rank = {t: i for i, t in enumerate(INSERT_ORDER)}

    removals, creations, updates = [], [], []
    for change in changes:
        op = change["op"]
        if op == "update":
            updates.append(change)
        elif (op == "insert") == forward:
            creations.append(change)
        else:
            removals.append(change)
    removals.sort(key=lambda c: -rank.get(c["table"], 0))
    creations.sort(key=lambda c: rank.get(c["table"], 0))

    # 1. remove rows that did not exist in the target state (edges before devices)
    for change in removals:
        obj = await _current(db, change)
        if obj is None:
            continue
        expected = change["after"] if change["op"] == "insert" else change["before"]
        if not force and _differs(obj, {k: v for k, v in expected.items() if k != "revision"}):
            conflicts.append(f"{change['table']} {change.get('name') or change['pk']}")
            continue
        await db.delete(obj)
    await db.flush()

    # 2. put back rows that existed in the target state (devices before edges)
    deferred_parents: list[tuple[Any, Any]] = []
    for change in creations:
        values = change["after"] if change["op"] == "insert" else change["before"]
        model = MODELS[change["table"]]
        existing = await _current(db, change)
        if existing is not None:
            _apply_values(existing, values)  # a cascade the database never performed
            continue
        obj = model()
        _apply_values(obj, values)
        pk_col = model.__table__.primary_key.columns.values()[0]
        setattr(obj, pk_col.name, _pk_value(model, change["pk"]))
        if isinstance(obj, GraphDevice) and obj.case_parent_id:
            deferred_parents.append((obj, obj.case_parent_id))
            obj.case_parent_id = None
        db.add(obj)
    await db.flush()
    for obj, parent_id in deferred_parents:
        obj.case_parent_id = parent_id

    # 3. changed columns go back (undo) or forward (redo)
    for change in updates:
        obj = await _current(db, change)
        if obj is None:
            conflicts.append(f"{change['table']} {change.get('name') or change['pk']} (gone)")
            continue
        expected = change["after"] if not forward else change["before"]
        target = change["before"] if not forward else change["after"]
        if not force and _differs(obj, expected):
            conflicts.append(f"{change['table']} {change.get('name') or change['pk']}")
            continue
        _apply_values(obj, target)
    if conflicts and not force:
        await db.rollback()
        raise HTTPException(
            status.HTTP_409_CONFLICT,
            detail={
                "message": "Some items changed outside the history since this step",
                "conflicts": conflicts[:20],
            },
        )
    await db.flush()


async def _step_nocommit(
    db: AsyncSession, kind: str, scope_id: uuid.UUID, *, undo: bool, force: bool
) -> HistoryEntry | None:
    """Undo the newest live entry or redo the oldest undone one, without committing."""
    query = select(HistoryEntry).where(
        HistoryEntry.scope_kind == kind,
        HistoryEntry.scope_id == scope_id,
        HistoryEntry.undone.is_(not undo),
    )
    # undo takes the newest live entry, redo the oldest undone one
    query = query.order_by(HistoryEntry.seq.desc() if undo else HistoryEntry.seq.asc()).limit(1)
    target = await db.scalar(query)
    if target is None:
        return None
    with recorder.suppress():
        await _apply(db, target.changes, forward=not undo, force=force)
    target.undone = undo
    return target


async def step(
    db: AsyncSession, kind: str, scope_id: uuid.UUID, *, undo: bool, force: bool = False
) -> HistoryEntry | None:
    """Undo the newest live entry, or redo the oldest undone one. Returns it, or None if none."""
    target = await _step_nocommit(db, kind, scope_id, undo=undo, force=force)
    if target is not None:
        await db.commit()
    return target


async def restore(
    db: AsyncSession, kind: str, scope_id: uuid.UUID, seq: int, *, force: bool = False
) -> int:
    """Move the state to just after entry ``seq`` (0 = before every recorded change).

    All steps run in one transaction: a conflict part-way rolls the whole restore back, so the data
    is never left between two versions.
    """
    rows = await entries(db, kind, scope_id)
    if seq != 0 and seq not in {e.seq for e in rows}:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "No such version")
    steps = 0
    cursor = cursor_of(rows)
    while cursor != seq:
        undo = cursor > seq
        target = await _step_nocommit(db, kind, scope_id, undo=undo, force=force)
        if target is None:
            break
        steps += 1
        cursor = target.seq - 1 if undo else target.seq
        # an undone entry lowers the cursor to the next live one, which may be several below
        if undo:
            live = await db.scalar(
                select(func.max(HistoryEntry.seq)).where(
                    HistoryEntry.scope_kind == kind,
                    HistoryEntry.scope_id == scope_id,
                    HistoryEntry.undone.is_(False),
                )
            )
            cursor = live or 0
    await db.commit()
    return steps
