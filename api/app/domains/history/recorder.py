"""Capture the row changes a write request makes, so they can be undone.

How it works
------------
``HistoryMiddleware`` opens a ``Recorder`` for every write request (POST/PUT/PATCH/DELETE under
``/api/v1``) and keeps it in a ``ContextVar``. A global SQLAlchemy ``after_flush`` listener adds
every change to a *tracked* model to the active recorder (session-agnostic: the request's own
session and the graph-sync session both feed it). When the response is a success the middleware
turns the recorder into one ``HistoryEntry`` per scope (job / venue).

What is recorded is the net row diff: for an update only the changed columns (old and new), for an
insert the full new row, for a delete the full old row. Rows the database removes by itself (an
edge when its device is deleted, a child's ``case_parent_id`` set to NULL) never reach the
session, so ``before_flush`` queries and records them explicitly; without that an undo of a device
delete would bring the device back without its cables.

Applying the *exact* inverse (rather than re-running the request) is what makes undo reliable: the
derived edges the sync drew are part of the diff, so nothing has to be recomputed.
"""

from __future__ import annotations

import uuid
from contextvars import ContextVar
from dataclasses import dataclass, field
from datetime import date, datetime
from typing import Any

from sqlalchemy import event, inspect, select
from sqlalchemy.orm import Session, attributes

from app.domains.audio.models import ProductionJob
from app.domains.graph.models import ConnectionEdge, GraphDevice
from app.domains.venues.models import Venue, VenuePowerGroup, VenuePowerOutlet

# model -> ops that are recorded. A job or venue itself is only ever *edited* here (its title,
# dates, notes ...): creating one has nothing to undo to, and deleting one purges its history
# (``service.purge``, called from the delete paths) because nothing is left to restore into.
TRACKED: dict[type, frozenset[str]] = {
    GraphDevice: frozenset({"insert", "update", "delete"}),
    ConnectionEdge: frozenset({"insert", "update", "delete"}),
    ProductionJob: frozenset({"update"}),
    Venue: frozenset({"update"}),
    VenuePowerGroup: frozenset({"insert", "update", "delete"}),
    VenuePowerOutlet: frozenset({"insert", "update", "delete"}),
}
# columns that change on every write and must not be restored verbatim (optimistic-lock counter)
SKIP_COLUMNS = frozenset({"revision"})


def scope_of(obj: Any) -> tuple[str, uuid.UUID] | None:
    """Which history an object belongs to: ``("job", id)`` or ``("venue", id)``."""
    if isinstance(obj, ProductionJob):
        return ("job", obj.id)
    if isinstance(obj, Venue):
        return ("venue", obj.id)
    if isinstance(obj, (VenuePowerGroup, VenuePowerOutlet)):
        return ("venue", obj.venue_id) if obj.venue_id else None
    job_id = getattr(obj, "job_id", None)
    venue_id = getattr(obj, "venue_id", None)
    if job_id:
        return ("job", job_id)
    if venue_id:
        return ("venue", venue_id)
    return None


def to_json(value: Any) -> Any:
    if isinstance(value, uuid.UUID):
        return str(value)
    if isinstance(value, (datetime, date)):
        return value.isoformat()
    return value


def from_json(column: Any, value: Any) -> Any:
    """Undo ``to_json`` using the column's own type (UUID and datetime need real objects)."""
    if value is None:
        return None
    try:
        python_type = column.type.python_type
    except NotImplementedError:
        return value
    if python_type is uuid.UUID and not isinstance(value, uuid.UUID):
        return uuid.UUID(str(value))
    if python_type is datetime and isinstance(value, str):
        return datetime.fromisoformat(value)
    if python_type is date and isinstance(value, str):
        # a Date column (a job's start / end date): SQLite refuses an ISO string for it
        return date.fromisoformat(value[:10])
    return value


@dataclass
class Change:
    table: str
    pk: str
    op: str  # insert | update | delete
    scope: tuple[str, str]
    before: dict = field(default_factory=dict)
    after: dict = field(default_factory=dict)
    name: str = ""

    def as_json(self) -> dict:
        return {
            "table": self.table,
            "pk": self.pk,
            "op": self.op,
            "before": self.before,
            "after": self.after,
            "name": self.name,
        }


class Recorder:
    def __init__(self) -> None:
        self.changes: dict[tuple[str, str], Change] = {}
        self.order: list[tuple[str, str]] = []
        self.suppressed = False

    def add(self, change: Change) -> None:
        """Merge into what this request already did to the same row (net effect only)."""
        key = (change.table, change.pk)
        known = self.changes.get(key)
        if known is None:
            self.changes[key] = change
            self.order.append(key)
            return
        if known.op == "insert" and change.op == "delete":
            del self.changes[key]  # created and removed in one request: nothing to undo
            self.order.remove(key)
            return
        if known.op == "insert":  # insert + update = an insert of the final row
            known.after = {**known.after, **change.after}
            return
        if change.op == "delete":  # update + delete = delete of the original row
            known.op = "delete"
            known.before = {**change.before, **known.before}
            known.after = {}
            return
        for column, value in change.before.items():
            known.before.setdefault(column, value)
        known.after = {**known.after, **change.after}
        if known.op == "delete" and change.op == "insert":  # delete + re-insert = an update
            known.op = "update"

    def result(self) -> list[Change]:
        return [self.changes[k] for k in self.order if self._net(self.changes[k])]

    @staticmethod
    def _net(change: Change) -> bool:
        if change.op != "update":
            return True
        return any(change.before.get(k) != v for k, v in change.after.items())


_recorder: ContextVar[Recorder | None] = ContextVar("history_recorder", default=None)


def current() -> Recorder | None:
    rec = _recorder.get()
    return None if rec is None or rec.suppressed else rec


def start() -> tuple[Recorder, Any]:
    rec = Recorder()
    return rec, _recorder.set(rec)


def stop(token: Any) -> None:
    _recorder.reset(token)


def suppress() -> Any:
    """Context manager-ish: restores and replays must not record themselves."""
    rec = _recorder.get()
    previous = rec.suppressed if rec else False
    if rec:
        rec.suppressed = True

    class _Restore:
        def __enter__(self) -> None:
            return None

        def __exit__(self, *exc: Any) -> None:
            if rec:
                rec.suppressed = previous

    return _Restore()


def _columns(obj: Any) -> list[str]:
    return [a.key for a in inspect(obj).mapper.column_attrs]


def _snapshot(obj: Any) -> dict:
    state = inspect(obj)
    return {
        key: to_json(state.dict.get(key))
        for key in _columns(obj)
        if key not in SKIP_COLUMNS and key in state.dict
    }


def _pk(obj: Any) -> str:
    return str(inspect(obj).identity[0] if inspect(obj).identity else getattr(obj, "id", ""))


def _name(obj: Any) -> str:
    for key in ("name", "title"):
        value = getattr(obj, key, None)
        if isinstance(value, str) and value:
            return value
    return ""


def _record_cascades(session: Session, rec: Recorder, device: GraphDevice) -> None:
    """Rows the database changes on its own when ``device`` is deleted (see module docstring)."""
    with session.no_autoflush:
        edges = session.scalars(
            select(ConnectionEdge).where(
                (ConnectionEdge.src_device_id == device.id)
                | (ConnectionEdge.dst_device_id == device.id)
            )
        ).all()
        children = session.scalars(
            select(GraphDevice).where(GraphDevice.case_parent_id == device.id)
        ).all()
    for edge in edges:
        if edge in session.deleted:
            continue
        scope = scope_of(edge)
        if scope:
            rec.add(
                Change(
                    "graph_connection_edges",
                    _pk(edge),
                    "delete",
                    (scope[0], str(scope[1])),
                    before=_snapshot(edge),
                )
            )
    for child in children:
        scope = scope_of(child)
        if scope and child.id != device.id:
            rec.add(
                Change(
                    "graph_devices",
                    _pk(child),
                    "update",
                    (scope[0], str(scope[1])),
                    before={"case_parent_id": str(device.id)},
                    after={"case_parent_id": None},
                    name=_name(child),
                )
            )


@event.listens_for(Session, "before_flush")
def _before_flush(session: Session, flush_context: Any, instances: Any) -> None:
    rec = current()
    if rec is None:
        return
    for obj in list(session.deleted):
        if isinstance(obj, GraphDevice):
            _record_cascades(session, rec, obj)


@event.listens_for(Session, "after_flush")
def _after_flush(session: Session, flush_context: Any) -> None:
    rec = current()
    if rec is None:
        return
    for obj in session.new:
        ops = TRACKED.get(type(obj))
        scope = scope_of(obj) if ops else None
        if ops and "insert" in ops and scope:
            rec.add(
                Change(
                    inspect(obj).mapper.local_table.name,
                    _pk(obj),
                    "insert",
                    (scope[0], str(scope[1])),
                    after=_snapshot(obj),
                    name=_name(obj),
                )
            )
    for obj in session.dirty:
        ops = TRACKED.get(type(obj))
        scope = scope_of(obj) if ops else None
        if not (ops and "update" in ops and scope) or not session.is_modified(obj):
            continue
        before: dict = {}
        after: dict = {}
        state = inspect(obj)
        for key in _columns(obj):
            if key in SKIP_COLUMNS:
                continue
            hist = attributes.get_history(obj, key, passive=attributes.PASSIVE_NO_INITIALIZE)
            if not hist.has_changes():
                continue
            after[key] = to_json(state.dict.get(key))
            # The old value is known only when the attribute was loaded before it was set. If it was
            # not, leave it out of ``before`` rather than record None: an undo then skips that
            # column instead of writing NULL over real data.
            if hist.deleted:
                before[key] = to_json(hist.deleted[0])
        if after:
            rec.add(
                Change(
                    inspect(obj).mapper.local_table.name,
                    _pk(obj),
                    "update",
                    (scope[0], str(scope[1])),
                    before=before,
                    after=after,
                    name=_name(obj),
                )
            )
    for obj in session.deleted:
        ops = TRACKED.get(type(obj))
        scope = scope_of(obj) if ops else None
        if ops and "delete" in ops and scope:
            rec.add(
                Change(
                    inspect(obj).mapper.local_table.name,
                    _pk(obj),
                    "delete",
                    (scope[0], str(scope[1])),
                    before=_snapshot(obj),
                    name=_name(obj),
                )
            )
