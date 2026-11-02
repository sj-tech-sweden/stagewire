"""The power sheet: the power tree, what is plugged into it and the cables and extension cords
it takes.

Everything comes from the same evaluation the rigging editor shows (``rigging_summary``), plus the
graph, which holds what only the graph knows: where nodes sit on the plot and the length and
Stockwire product of an extension cord. A cable is needed for a device that takes its power through
a detachable lead (IEC C13 by default); a device with a fixed cable only needs the node outlet.
"""

import math
from typing import Any
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.domains.audio.models import AudioDevice
from app.domains.graph import power_native
from app.domains.graph.backfill import backfill_job
from app.domains.graph.models import GraphDevice
from app.domains.rigging import connectors
from app.domains.rigging import router as rigging_router
from app.domains.venues.models import VenuePowerOutlet

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


async def power_sheet_context(db: AsyncSession, job_id: UUID) -> dict[str, Any]:
    from app.domains.reports.registry import _load_job

    await backfill_job(db, job_id)
    job = await _load_job(db, job_id)
    summary = await rigging_router.rigging_summary(job_id, db)
    graph = {
        str(row.legacy_ref): row
        for row in await db.scalars(select(GraphDevice).where(GraphDevice.job_id == job_id))
        if row.legacy_ref
    }
    devices = {
        str(d.id): d
        for d in await db.scalars(select(AudioDevice).where(AudioDevice.job_id == job_id))
    }
    nodes = {n["id"]: n for n in summary["nodes"]}
    settings = cable_settings(job)
    outlets = {
        str(o.id): o
        for o in await db.scalars(
            select(VenuePowerOutlet).where(VenuePowerOutlet.venue_id == job.venue_id)
        )
    }
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
        gear_ref = {"fixture": "lighting_fixtures", "element": "stage_plot_elements"}.get(
            load["kind"], "audio_devices"
        )
        gear_node = graph.get(f"{gear_ref}:{load['id']}") or (
            graph.get(f"audio_devices:{load['device_id']}") if load.get("device_id") else None
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


def _cord_counts(cords: list[dict]) -> dict[Any, int]:
    counts: dict[Any, int] = {}
    for cord in cords:
        key = cord["length_m"] if cord["length_m"] != "" else "?"
        counts[key] = counts.get(key, 0) + 1
    return counts
