"""Report contexts built from the unified graph.

Same rows as the legacy ``_channel_list_context`` / ``_patch_sheet_context`` in
``registry.py`` (which read the audio tables), so a report can switch data source.
"""

from typing import Any
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.domains.audio.wwb import wireless_frequency_summary
from app.domains.graph import plot_native
from app.domains.graph.models import ConnectionEdge, GraphDevice
from app.domains.graph.readers import channel_view


def _performer_names(devices: list[Any], edges: list[Any]) -> dict[str, str]:
    """Channel node id -> label of the performer element linked to it."""
    labels = {
        str(d.id): (d.attributes or {}).get("label")
        for d in devices
        if d.kind == "plot_element" and (d.attributes or {}).get("element_type") == "performer"
    }
    names: dict[str, str] = {}
    for edge in sorted(edges, key=lambda e: str(e.id)):
        label = labels.get(str(edge.src_device_id))
        if edge.signal == "link" and (edge.attributes or {}).get("role") == "channel" and label:
            names[str(edge.dst_device_id)] = label
    return names


def _lists(devices: list[Any]) -> list[Any]:
    return sorted((d for d in devices if d.kind == "channel_list"), key=lambda d: d.position)


def _in_list(devices: list[Any], kind: str, list_id: Any) -> list[Any]:
    return [
        d for d in devices if d.kind == kind and (d.attributes or {}).get("list_id") == str(list_id)
    ]


def channel_rows(devices: list[Any], edges: list[Any]) -> list[dict]:
    performers = _performer_names(devices, edges)
    rows = []
    for channel_list in _lists(devices):
        nodes = sorted(
            _in_list(devices, "channel", channel_list.id),
            key=lambda d: channel_view(d).channel_number,
        )
        for node in nodes:
            channel = channel_view(node)
            performer = performers.get(str(node.id)) or channel.performer_name or ""
            rows.append(
                {
                    "channel_number": channel.channel_number,
                    "source_label": channel.source_label,
                    "device": channel.device or "",
                    "input_details": " · ".join(
                        v
                        for v in (
                            channel.input_type or "",
                            channel.instrument_group or "",
                            channel.stand_type or "",
                        )
                        if v
                    ),
                    "performer_name": performer,
                    "wireless_pack": channel.wireless_pack or "",
                    "wireless_frequency_mhz": channel.wireless_frequency_mhz,
                    "wireless_group": channel.wireless_group or "",
                    "wireless_channel": channel.wireless_channel or "",
                    "wireless_details": " · ".join(
                        v
                        for v in (
                            performer,
                            channel.wireless_pack or "",
                            wireless_frequency_summary(
                                channel.wireless_frequency_mhz,
                                channel.wireless_group,
                                channel.wireless_channel,
                            ),
                        )
                        if v
                    ),
                    "connector": channel.connector or "",
                    "phantom_power": channel.phantom_power,
                    "notes": channel.notes,
                    "list_name": channel_list.name,
                }
            )
    return rows


def _chain_points(node: Any, edges: list[Any]) -> list[dict]:
    """Patch points of one chain (an input channel or an output bus), in order."""
    points = []
    for edge in edges:
        attrs = edge.attributes or {}
        if attrs.get("chain") != str(node.id):
            continue
        if "first_point" in attrs:
            points.append({**attrs["first_point"], "device_id": str(edge.src_device_id)})
        elif edge.dst_device_id != node.id:
            points.append({**attrs, "device_id": str(edge.dst_device_id)})
    return sorted(points, key=lambda p: p.get("position") or 0)


def patch_sheets(devices: list[Any], edges: list[Any]) -> list[dict]:
    performers = _performer_names(devices, edges)
    by_id = {str(d.id): d for d in devices}
    names = {key: d.name for key, d in by_id.items()}
    sheets: dict[str, dict] = {}

    def console_patch(points: list[dict]) -> str:
        return next(
            (
                p.get("patch_label") or ""
                for p in points
                if (device := by_id.get(p["device_id"])) and device.kind == "mixer"
            ),
            "",
        )

    def public_id(graph_id: str) -> str:
        """Sheets are selected by the legacy device id, so keep it when there is one."""
        ref = getattr(by_id.get(graph_id), "legacy_ref", None) or ""
        table, _, legacy_id = ref.partition(":")
        return legacy_id if table == "device" and legacy_id else graph_id

    def add_row(point: dict, row: dict) -> None:
        key = point["device_id"]
        sheet = sheets.setdefault(
            key,
            {
                "id": public_id(key),
                "name": names.get(key) or key,
                "type": point.get("point_type") or "mixer",
                "rows": [],
            },
        )
        sheet["rows"].append(row)

    for channel_list in _lists(devices):
        for node in sorted(
            _in_list(devices, "channel", channel_list.id),
            key=lambda d: channel_view(d).channel_number,
        ):
            channel = channel_view(node)
            points = _chain_points(node, edges)
            for point in points:
                add_row(
                    point,
                    {
                        "direction": "In",
                        "channel_number": channel.channel_number,
                        "source_label": channel.source_label,
                        "instrument_group": channel.instrument_group,
                        "device": channel.device or "",
                        "stand_type": channel.stand_type,
                        "performer_name": performers.get(str(node.id))
                        or channel.performer_name
                        or "",
                        "wireless_pack": channel.wireless_pack or "",
                        "wireless_frequency_mhz": channel.wireless_frequency_mhz,
                        "wireless_group": channel.wireless_group or "",
                        "wireless_channel": channel.wireless_channel or "",
                        "phantom_power": channel.phantom_power,
                        "patch_assignment": " / ".join(
                            v
                            for v in (names.get(point["device_id"], ""), console_patch(points))
                            if v
                        ),
                        "patch_label": point.get("patch_label") or "",
                        "connector": point.get("connector") or "",
                        "notes": " · ".join(
                            v for v in (channel.notes, point.get("notes") or "") if v
                        ),
                    },
                )
        for bus in sorted(_in_list(devices, "output", channel_list.id), key=lambda d: d.position):
            points = _chain_points(bus, edges)
            for point in points:
                add_row(
                    point,
                    {
                        "direction": "Out",
                        "channel_number": "OUT",
                        "source_label": bus.name,
                        "instrument_group": "",
                        "device": "",
                        "stand_type": "",
                        "performer_name": "",
                        "wireless_pack": "",
                        "wireless_frequency_mhz": None,
                        "wireless_group": "",
                        "wireless_channel": "",
                        "phantom_power": False,
                        "bus_connector": point.get("bus_connector") or "",
                        "patch_assignment": " / ".join(
                            v
                            for v in (names.get(point["device_id"], ""), console_patch(points))
                            if v
                        ),
                        "patch_label": point.get("patch_label") or "",
                        "connector": point.get("connector") or "",
                        "notes": " · ".join(
                            v for v in (bus.notes or "", point.get("notes") or "") if v
                        ),
                    },
                )
    return [
        {**sheet, "rows": sorted(sheet["rows"], key=lambda row: row["direction"] != "In")}
        for sheet in sorted(sheets.values(), key=lambda value: value["name"].lower())
    ]


async def load_graph(
    db: AsyncSession, job_id: UUID
) -> tuple[list[GraphDevice], list[ConnectionEdge], list]:
    devices = (await db.scalars(select(GraphDevice).where(GraphDevice.job_id == job_id))).all()
    edges = (await db.scalars(select(ConnectionEdge).where(ConnectionEdge.job_id == job_id))).all()
    return list(devices), list(edges), await plot_native.load_elements(db, job_id)
