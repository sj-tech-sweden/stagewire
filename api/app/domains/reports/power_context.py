"""The power sheet: the power tree, what is plugged into it and the cables and extension cords
it takes.

Everything comes from the same evaluation the rigging editor shows (``rigging_summary``), plus the
graph, which holds what only the graph knows: where nodes sit on the plot and the length and
Stockwire product of an extension cord. A cable is needed for a device that takes its power through
a detachable lead (IEC C13 by default); a device with a fixed cable only needs the node outlet.
"""

import math
from collections import defaultdict
from typing import Any
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.domains.graph import devices_native, fixtures_native, plot_native, power_native
from app.domains.graph.backfill import backfill_job
from app.domains.graph.ids import public_id
from app.domains.graph.models import GraphDevice
from app.domains.reports.context import JobOrVenue, load_subject
from app.domains.rigging import connectors
from app.domains.rigging import router as rigging_router
from app.domains.venues.models import VenuePowerGroup, VenuePowerOutlet
from app.domains.venues.power_load import summarize_venue_power

# Standard cord lengths in metres; a needed length is rounded up to one of them.
CORD_LENGTHS = (2, 5, 10, 15, 20, 25, 30, 50)

INLET_LABELS = {
    "": "IEC C13",
    "iec_c13": "IEC C13",
    "attached_schuko": "Fixed cable, Schuko",
    "powercon": "powerCON",
    "cee16": "CEE 16 A",
    "none": "No power",
    "other": "Other",
}


def cord_for(metres: float, lengths: tuple[float, ...] = CORD_LENGTHS) -> float:
    found = next((length for length in sorted(lengths) if length >= metres), None)
    return _metres(found if found is not None else math.ceil(metres))


def cable_settings(job: Any) -> dict:
    """Slack and standard lengths as set for the job's cable plan (same defaults as the web)."""
    saved = ((getattr(job, "cable_plan", None) or {}).get("settings")) or {}
    lengths = saved.get("standard_lengths_m") or [1, 2, 3, 5, 7.5, 10, 15, 20, 30, 50]
    return {
        "slack_pct": float(saved.get("slack_pct", 10)),
        "slack_m": float(saved.get("slack_m", 1)),
        "lengths": tuple(float(x) for x in lengths),
    }


def run_length(distance_m: float, settings: dict) -> float:
    """The standard cable length for a run: the distance plus slack, rounded up to a length."""
    needed = distance_m * (1 + settings["slack_pct"] / 100) + settings["slack_m"]
    return cord_for(needed, settings["lengths"])


def _metres(value: Any) -> Any:
    """10.0 reads as 10 on a sheet; other values stay as they are."""
    if isinstance(value, float) and value.is_integer():
        return int(value)
    return value


def connector_label(key: str | None) -> str:
    if not key:
        return ""
    try:
        return connectors.connector(key).label
    except KeyError:
        return key


def cable_for(inlet: str | None, connector: str) -> str:
    """The lead a device needs to reach a node output of ``connector``."""
    inlet = (inlet or "").strip().lower()
    if inlet == "none":
        return ""
    target = connector_label(connector) or "node"
    if inlet in ("", "iec_c13"):
        return f"IEC C13 → {target}"
    if inlet == "attached_schuko":
        return "Fixed cable (Schuko)" if connector in ("", "schuko") else f"Fixed Schuko → {target}"
    return f"{INLET_LABELS.get(inlet, inlet)} → {target}"


def _spot(node: GraphDevice | None) -> tuple[float, float] | None:
    if node is None or node.canvas_x_cm is None or node.canvas_y_cm is None:
        return None
    return node.canvas_x_cm, node.canvas_y_cm


def _distance_m(a: tuple[float, float] | None, b: tuple[float, float] | None) -> float | None:
    if a is None or b is None:
        return None
    return math.hypot(a[0] - b[0], a[1] - b[1]) / 100


def _uuid(value: Any) -> UUID | None:
    try:
        return UUID(str(value)) if value else None
    except (ValueError, TypeError):
        return None


async def power_sheet_context(db: AsyncSession, context) -> dict[str, Any]:
    """The power sheet for a job or a venue base rig.

    A job walks its rigging tree (``rigging_summary``) and the graph devices; a venue has no
    ``ProductionJob`` and a different supply model (``venue_power_groups`` /
    ``venue_power_outlets``), built from ``summarize_venue_power`` and the venue's own graph
    devices. The two paths return the same shape so the template is untouched.
    """
    if isinstance(context, JobOrVenue) and context.is_venue:
        return await _venue_power_sheet_context(db, context)
    job_id = context.id if isinstance(context, JobOrVenue) else context
    return await _job_power_sheet_context(db, job_id)


async def _job_power_sheet_context(db: AsyncSession, job_id: UUID) -> dict[str, Any]:
    from app.domains.reports.registry import _load_job

    await backfill_job(db, job_id)
    job = await _load_job(db, job_id)
    summary = await rigging_router.rigging_summary(job_id=job_id, venue_id=None, db=db)
    graph = {
        str(row.legacy_ref): row
        for row in await db.scalars(select(GraphDevice).where(GraphDevice.job_id == job_id))
        if row.legacy_ref
    }
    devices = {str(d.id): d for d in await devices_native.load_devices(db, job_id)}
    nodes = {n["id"]: n for n in summary["nodes"]}
    settings = cable_settings(job)
    outlets = {
        str(o.id): o
        for o in await db.scalars(
            select(VenuePowerOutlet).where(VenuePowerOutlet.venue_id == job.venue_id)
        )
    }
    fixture_hosts = await fixtures_native.host_nodes(db, job_id)
    element_hosts = {public_id(n): n for n in await plot_native.element_nodes(db, job_id)}
    power_hosts = await power_native.host_nodes(db, job_id)
    power_rows = {str(pid): power_native.node_view(pid, host) for pid, host in power_hosts.items()}

    def node_graph(node_id: str | None) -> GraphDevice | None:
        return power_hosts.get(UUID(str(node_id))) if node_id else None

    tree_rows: list[dict] = []
    cords: list[dict] = []
    for node in summary["nodes"]:
        row = node_graph(node["id"])
        parent = nodes.get(node["parent_id"]) if node["parent_id"] else None
        length = _metres((row.attributes or {}).get("length_m")) if row else None
        if length is None and parent and node["kind"] != "extension":
            metres = _distance_m(_spot(node_graph(parent["id"])), _spot(row))
            length = run_length(metres, settings) if metres is not None else None
        tree_rows.append(
            {
                "name": node["name"],
                "kind": node["kind"],
                "fed_from": parent["name"] if parent else "",
                "connector": connector_label(node["feed_connector"]),
                "rating_amps": node["rating_amps"] if node["rating_amps"] is not None else "",
                "load_w": round(sum(node["watts"].values())),
                "peak_amps": max(node["amps"].values()),
                "status": node["status"],
                "length_m": length if length is not None else "",
            }
        )
        if node["kind"] == "extension":
            cords.append(
                {
                    "name": node["name"],
                    "from": parent["name"] if parent else "",
                    "to": ", ".join(
                        n["name"] for n in summary["nodes"] if n["parent_id"] == node["id"]
                    ),
                    "connector": connector_label(node["feed_connector"]),
                    "length_m": length if length is not None else "",
                    "product": (row.stockwire_product_name if row else "") or "",
                }
            )

    def node_spot(node_id: str, toward: tuple[float, float] | None) -> tuple[float, float] | None:
        """Where a power node is on the plot: its own place, else its venue outlet, else (a
        venue group) the outlet of that group nearest to what is plugged in."""
        spot = _spot(node_graph(node_id))
        if spot is not None:
            return spot
        row = power_rows.get(node_id)
        if row is None:
            return None
        if row.venue_outlet_id and str(row.venue_outlet_id) in outlets:
            o = outlets[str(row.venue_outlet_id)]
            return (o.x_cm, o.y_cm) if o.x_cm is not None and o.y_cm is not None else None
        if row.venue_group_id:
            placed = [
                (o.x_cm, o.y_cm)
                for o in outlets.values()
                if o.group_id == row.venue_group_id and o.x_cm is not None and o.y_cm is not None
            ]
            if placed and toward is not None:
                return min(placed, key=lambda p: math.hypot(p[0] - toward[0], p[1] - toward[1]))
            return placed[0] if placed else None
        return None

    load_rows: list[dict] = []
    needed: dict[str, int] = {}
    for load in summary["loads"]:
        device = devices.get(load["device_id"]) if load.get("device_id") else None
        inlet = device.power_inlet if device else ""
        node = nodes.get(load["power_node_id"]) if load["power_node_id"] else None
        cable = cable_for(inlet, load["power_connector"]) if node else ""
        if load["kind"] == "fixture":
            gear_found = fixture_hosts.get(UUID(load["id"]))
        elif load["kind"] == "element":
            gear_found = element_hosts.get(UUID(load["id"]))
        else:
            gear_found = graph.get(f"device:{load['id']}")
        gear_node = gear_found or (
            graph.get(f"device:{load['device_id']}") if load.get("device_id") else None
        )
        gear_spot = _spot(gear_node)
        metres = (
            _distance_m(node_spot(load["power_node_id"], gear_spot), gear_spot) if node else None
        )
        length = run_length(metres, settings) if metres is not None else None
        if cable:
            label = f"{cable} {length} m" if length is not None else cable
            needed[label] = needed.get(label, 0) + 1
        load_rows.append(
            {
                "device": load["label"],
                "type": load["kind"],
                "inlet": INLET_LABELS.get((inlet or "").lower(), inlet or "IEC C13"),
                "plugged_into": node["name"] if node else "",
                "connector": connector_label(load["power_connector"]),
                "power_w": load["power_w"] if load["power_w"] is not None else "",
                "cable": cable or "Not plugged in",
                "length_m": length if length is not None else "",
                "status": load["power_status"],
            }
        )
    cable_rows = [{"cable": name, "count": count} for name, count in sorted(needed.items())]
    for length, count in sorted(_cord_counts(cords).items()):
        cable_rows.append({"cable": f"Extension cord {length} m", "count": count})
    return {
        "job": job,
        "power_tree": tree_rows,
        "power_loads": load_rows,
        "power_cords": cords,
        "power_cables": cable_rows,
    }


async def _venue_power_sheet_context(db: AsyncSession, context: JobOrVenue) -> dict[str, Any]:
    """The power sheet for a venue's Standard Base Rig.

    The venue has no ``rigging_summary``; its supply is the ``venue_power_groups`` /
    ``venue_power_outlets`` tree, and the device that hangs off it stores its draw on
    ``attributes.power_w`` plus the outlet or group it plugs into (``attributes.venue_outlet_id`` /
    ``venue_group_id``). ``summarize_venue_power`` rolls those watts up the tree and flags
    over-limit nodes; the per-device rows and cables reuse the same helpers as the job path. A
    venue supply node has no feed connector or extension, so those fields are left blank and match
    what the template renders for a job without them.
    """
    venue_id = context.id
    job = await load_subject(db, context)
    settings = cable_settings(job)

    nodes = (
        await db.scalars(
            select(GraphDevice).where(
                GraphDevice.venue_id == venue_id, GraphDevice.job_id.is_(None)
            )
        )
    ).all()
    groups = (
        await db.scalars(select(VenuePowerGroup).where(VenuePowerGroup.venue_id == venue_id))
    ).all()
    outlets = (
        await db.scalars(select(VenuePowerOutlet).where(VenuePowerOutlet.venue_id == venue_id))
    ).all()
    group_by_id = {g.id: g for g in groups}
    outlet_by_id = {o.id: o for o in outlets}

    outlet_watts: dict[UUID, float] = defaultdict(float)
    group_direct_watts: dict[UUID, float] = defaultdict(float)
    device_plug: dict[UUID, tuple[str, UUID, float, dict]] = {}
    for node in nodes:
        info = _venue_device_power(node)
        if info["watts"] is None:
            continue
        if info["outlet_id"] and info["outlet_id"] in outlet_by_id:
            outlet_watts[info["outlet_id"]] += info["watts"]
            device_plug[node.id] = ("outlet", info["outlet_id"], info["watts"], info)
        elif info["group_id"] and info["group_id"] in group_by_id:
            group_direct_watts[info["group_id"]] += info["watts"]
            device_plug[node.id] = ("group", info["group_id"], info["watts"], info)

    summary = summarize_venue_power(groups, outlets, dict(outlet_watts), dict(group_direct_watts))
    element_by_id = {e.id: e for e in (*summary.outlets, *summary.groups)}

    def depth(group: VenuePowerGroup) -> int:
        d, cur = 0, group.parent_id
        while cur in group_by_id and d < 50:
            d += 1
            cur = group_by_id[cur].parent_id
        return d

    tree_rows: list[dict] = []
    for g in sorted(groups, key=lambda g: (depth(g), g.name or "")):
        e = element_by_id.get(g.id)
        parent = group_by_id[g.parent_id].name if g.parent_id in group_by_id else ""
        tree_rows.append(
            {
                "name": g.name or "",
                "kind": g.kind,
                "fed_from": parent,
                "connector": "",
                "rating_amps": g.rating_amps if g.rating_amps is not None else "",
                "load_w": round(e.watts) if e else 0,
                "peak_amps": round(e.amps, 2) if e else 0.0,
                "status": "over" if (e and e.over) else "ok",
                "length_m": "",
            }
        )
    for o in sorted(
        outlets,
        key=lambda o: (
            group_by_id[o.group_id].name if o.group_id in group_by_id else "",
            o.name or "",
        ),
    ):
        e = element_by_id.get(o.id)
        fed = group_by_id[o.group_id].name if o.group_id in group_by_id else ""
        tree_rows.append(
            {
                "name": o.name or "",
                "kind": "outlet",
                "fed_from": fed,
                "connector": connector_label(o.connector),
                "rating_amps": o.rating_amps if o.rating_amps is not None else "",
                "load_w": round(e.watts) if e else 0,
                "peak_amps": round(e.amps, 2) if e else 0.0,
                "status": "over" if (e and e.over) else "ok",
                "length_m": "",
            }
        )

    load_rows: list[dict] = []
    needed: dict[str, int] = {}
    for node_id, (kind, target_id, watts, info) in device_plug.items():
        target = outlet_by_id.get(target_id) if kind == "outlet" else group_by_id.get(target_id)
        if target is None:
            continue
        node = next((n for n in nodes if n.id == node_id), None)
        connector = target.connector if kind == "outlet" else ""
        cable = (
            cable_for(info["inlet"], connector)
            if connector
            else INLET_LABELS.get(info["inlet"] or "", info["inlet"] or "IEC C13")
        )
        gear_spot = _spot(node)
        target_spot = (
            (target.x_cm, target.y_cm)
            if getattr(target, "x_cm", None) is not None
            and getattr(target, "y_cm", None) is not None
            else None
        )
        metres = _distance_m(target_spot, gear_spot)
        length = run_length(metres, settings) if metres is not None else None
        if cable:
            label = f"{cable} {length} m" if length is not None else cable
            needed[label] = needed.get(label, 0) + 1
        load_rows.append(
            {
                "device": info["name"],
                "type": "device",
                "inlet": INLET_LABELS.get(info["inlet"] or "", info["inlet"] or "IEC C13"),
                "plugged_into": target.name,
                "connector": connector_label(connector),
                "power_w": round(watts) if watts is not None else "",
                "cable": cable or "Not plugged in",
                "length_m": length if length is not None else "",
                "status": "ok",
            }
        )
    cable_rows = [{"cable": name, "count": count} for name, count in sorted(needed.items())]
    return {
        "job": job,
        "power_tree": tree_rows,
        "power_loads": load_rows,
        "power_cords": [],
        "power_cables": cable_rows,
    }


def _venue_device_power(node: GraphDevice) -> dict:
    """Power attributes of a venue base-rig device node (its draw and where it plugs in)."""
    a = node.attributes or {}
    raw = a.get("power_w")
    watts = None
    if raw is not None:
        try:
            watts = float(raw)
        except (TypeError, ValueError):
            watts = None
    return {
        "name": node.name or "",
        "inlet": (a.get("power_inlet") or "").strip().lower(),
        "connector": a.get("power_connector") or "",
        "outlet_id": _uuid(a.get("venue_outlet_id")),
        "group_id": _uuid(a.get("venue_group_id")),
        "watts": watts,
    }


def _cord_counts(cords: list[dict]) -> dict[Any, int]:
    counts: dict[Any, int] = {}
    for cord in cords:
        key = cord["length_m"] if cord["length_m"] != "" else "?"
        counts[key] = counts.get(key, 0) + 1
    return counts
