"""Cable routing for stage-plot reports.

Mirrors web/src/utils/cables.js so a report routes cables the same way the stage plot
does: cables run between devices in each signal chain, use cableways when that saves
distance, and avoid the audience area unless the detour is much longer.
"""

import math
from dataclasses import dataclass
from typing import Any

CABLEWAY_TRAVEL = 0.5
AUDIENCE_PENALTY = 3.0
SPEAKER_TYPES = {"speaker", "speaker_main", "speaker_sub", "speaker_delay", "monitor"}
MIC_TYPES = {"microphone", "di"}

Point = tuple[float, float]


@dataclass(frozen=True)
class Cable:
    key: str
    from_element_id: str | None = None
    from_device_id: str | None = None
    to_element_id: str | None = None
    to_device_id: str | None = None


def element_centre(element: Any) -> Point:
    """Elements rotate about their top-left corner, so the centre moves with the angle."""
    theta = math.radians(float(element.rotation or 0))
    half_w = float(element.width_cm or 0) / 2
    half_h = float(element.height_cm or 0) / 2
    x = float(element.position_x or 0)
    y = float(element.position_y or 0)
    return (
        x + half_w * math.cos(theta) - half_h * math.sin(theta),
        y + half_w * math.sin(theta) + half_h * math.cos(theta),
    )


def _ordered(points: Any) -> list[Any]:
    return sorted(points or [], key=lambda point: point.position or 0)


def _source_elements(channel_id: Any, elements: list[Any]) -> list[Any]:
    linked = [element for element in elements if element.linked_channel_id == channel_id]
    mics = [element for element in linked if element.element_type in MIC_TYPES]
    return mics or [element for element in linked if element.element_type == "performer"]


def derive_cables(
    channel_lists: list[Any], elements: list[Any], video_lists: list[Any]
) -> list[Cable]:
    cables: list[Cable] = []
    for channel_list in channel_lists:
        for channel in channel_list.channels:
            points = [point for point in _ordered(channel.patch_points) if point.device_id]
            if points:
                for element in _source_elements(channel.id, elements):
                    cables.append(
                        Cable(
                            key=f"src:{element.id}",
                            from_element_id=str(element.id),
                            to_device_id=str(points[0].device_id),
                        )
                    )
            for previous, current in zip(points, points[1:], strict=False):
                if previous.device_id != current.device_id:
                    cables.append(
                        Cable(
                            key=str(current.id),
                            from_device_id=str(previous.device_id),
                            to_device_id=str(current.device_id),
                        )
                    )
        for output in channel_list.outputs:
            points = [point for point in _ordered(output.points) if point.device_id]
            by_id = {str(point.id): point for point in points}
            for index, point in enumerate(points):
                parent = (
                    by_id.get(str(point.parent_id))
                    if point.parent_id
                    else (points[index - 1] if index > 0 else None)
                )
                if parent is not None and parent.device_id != point.device_id:
                    cables.append(
                        Cable(
                            key=str(point.id),
                            from_device_id=str(parent.device_id),
                            to_device_id=str(point.device_id),
                        )
                    )
    output_points = {
        str(point.id): point
        for channel_list in channel_lists
        for output in channel_list.outputs
        for point in output.points
    }
    for element in elements:
        if element.element_type not in SPEAKER_TYPES or not element.linked_output_point_id:
            continue
        point = output_points.get(str(element.linked_output_point_id))
        if point is None or not point.device_id:
            continue
        cables.append(
            Cable(
                key=f"spk:{element.id}",
                from_device_id=str(point.device_id),
                to_element_id=str(element.id),
            )
        )
    for video_list in video_lists:
        for video_input in video_list.inputs:
            points = [point for point in _ordered(video_input.patch_points) if point.device_id]
            if not points:
                continue
            for element in elements:
                if element.linked_video_input_id == video_input.id and (
                    element.element_type != "projector"
                ):
                    cables.append(
                        Cable(
                            key=f"src:{element.id}",
                            from_element_id=str(element.id),
                            to_device_id=str(points[0].device_id),
                        )
                    )
            for previous, current in zip(points, points[1:], strict=False):
                if previous.device_id != current.device_id:
                    cables.append(
                        Cable(
                            key=str(current.id),
                            from_device_id=str(previous.device_id),
                            to_device_id=str(current.device_id),
                        )
                    )
        for video_output in video_list.outputs:
            points = [point for point in _ordered(video_output.patch_points) if point.device_id]
            by_id = {str(point.id): point for point in points}
            for current in points:
                parent = by_id.get(str(current.parent_id)) if current.parent_id else None
                if parent is not None and parent.device_id != current.device_id:
                    cables.append(
                        Cable(
                            key=str(current.id),
                            from_device_id=str(parent.device_id),
                            to_device_id=str(current.device_id),
                        )
                    )
    return cables


def _distance(a: Point, b: Point) -> float:
    return math.hypot(b[0] - a[0], b[1] - a[1])


def _path_length(points: list[Point]) -> float:
    return sum(_distance(points[i - 1], points[i]) for i in range(1, len(points)))


def _project_on_segment(p: Point, a: Point, b: Point) -> Point:
    dx = b[0] - a[0]
    dy = b[1] - a[1]
    length_sq = dx * dx + dy * dy
    if length_sq == 0:
        return a
    t = max(0.0, min(1.0, ((p[0] - a[0]) * dx + (p[1] - a[1]) * dy) / length_sq))
    return (a[0] + t * dx, a[1] + t * dy)


def _segment_intersection(a: Point, b: Point, c: Point, d: Point) -> Point | None:
    rx = b[0] - a[0]
    ry = b[1] - a[1]
    sx = d[0] - c[0]
    sy = d[1] - c[1]
    denom = rx * sy - ry * sx
    if abs(denom) < 1e-9:
        return None
    qx = c[0] - a[0]
    qy = c[1] - a[1]
    t = (qx * sy - qy * sx) / denom
    u = (qx * ry - qy * rx) / denom
    eps = 1e-9
    if t < -eps or t > 1 + eps or u < -eps or u > 1 + eps:
        return None
    return (a[0] + t * rx, a[1] + t * ry)


def _node_key(p: Point) -> str:
    return f"{p[0]:.3f},{p[1]:.3f}"


def _point_in_polygon(p: Point, polygon: list[Point]) -> bool:
    inside = False
    j = len(polygon) - 1
    for i in range(len(polygon)):
        xi, yi = polygon[i]
        xj, yj = polygon[j]
        if (yi > p[1]) != (yj > p[1]) and p[0] < (xj - xi) * (p[1] - yi) / (yj - yi) + xi:
            inside = not inside
        j = i
    return inside


def _crossing_params(a: Point, b: Point, polygon: list[Point]) -> list[float]:
    params = []
    for i in range(len(polygon)):
        c = polygon[i]
        d = polygon[(i + 1) % len(polygon)]
        rx = b[0] - a[0]
        ry = b[1] - a[1]
        sx = d[0] - c[0]
        sy = d[1] - c[1]
        denom = rx * sy - ry * sx
        if abs(denom) < 1e-9:
            continue
        qx = c[0] - a[0]
        qy = c[1] - a[1]
        t = (qx * sy - qy * sx) / denom
        u = (qx * ry - qy * rx) / denom
        if 0 <= t <= 1 and 0 <= u <= 1:
            params.append(t)
    return params


def _inside_length(a: Point, b: Point, polygon: list[Point]) -> float:
    if len(polygon) < 3:
        return 0.0
    ts = sorted([0.0, *_crossing_params(a, b, polygon), 1.0])
    inside = 0.0
    for k in range(1, len(ts)):
        t0 = ts[k - 1]
        t1 = ts[k]
        if t1 - t0 < 1e-9:
            continue
        mid_t = (t0 + t1) / 2
        mid = (a[0] + mid_t * (b[0] - a[0]), a[1] + mid_t * (b[1] - a[1]))
        if _point_in_polygon(mid, polygon):
            inside += (t1 - t0) * _distance(a, b)
    return inside


def _open_cost(a: Point, b: Point, polygon: list[Point]) -> float:
    return _distance(a, b) + _inside_length(a, b, polygon) * (AUDIENCE_PENALTY - 1)


def _auto_route(
    start: Point,
    end: Point,
    cableways: list[list[Point]],
    audience: list[Point],
    tray_factor: float,
) -> list[Point] | None:
    lines = [line for line in cableways if len(line) >= 2]
    polygon = audience if len(audience) >= 3 else []
    if not lines and not polygon:
        return None

    segments: list[dict[str, Any]] = []
    for line in lines:
        for j in range(len(line) - 1):
            segments.append({"a": line[j], "b": line[j + 1], "extra": []})
    for i in range(len(segments)):
        for j in range(i + 1, len(segments)):
            crossing = _segment_intersection(
                segments[i]["a"], segments[i]["b"], segments[j]["a"], segments[j]["b"]
            )
            if crossing is not None:
                segments[i]["extra"].append(crossing)
                segments[j]["extra"].append(crossing)
    for segment in segments:
        segment["extra"].append(_project_on_segment(start, segment["a"], segment["b"]))
        segment["extra"].append(_project_on_segment(end, segment["a"], segment["b"]))

    pos: dict[str, Point] = {}
    adj: dict[str, list[tuple[str, float]]] = {}

    def add_edge(a: str, b: str, weight: float) -> None:
        adj.setdefault(a, []).append((b, weight))
        adj.setdefault(b, []).append((a, weight))

    tray_nodes: list[str] = []
    for segment in segments:
        unique_by_key: dict[str, Point] = {}
        for point in [segment["a"], segment["b"], *segment["extra"]]:
            unique_by_key[_node_key(point)] = point
        unique = sorted(unique_by_key.values(), key=lambda p: _distance(segment["a"], p))
        for point in unique:
            key = _node_key(point)
            if key not in pos:
                tray_nodes.append(key)
            pos[key] = point
        for k in range(1, len(unique)):
            add_edge(
                _node_key(unique[k - 1]),
                _node_key(unique[k]),
                _open_cost(unique[k - 1], unique[k], polygon) * tray_factor,
            )

    source, target = "__from", "__to"
    pos[source] = start
    pos[target] = end
    corners = []
    for index, corner in enumerate(polygon):
        key = f"__corner{index}"
        pos[key] = corner
        corners.append(key)
    open_nodes = [source, target, *corners]
    every_node = [*tray_nodes, *open_nodes]
    for a in open_nodes:
        for b in every_node:
            if a == b:
                continue
            if any(neighbour == b for neighbour, _ in adj.get(a, [])):
                continue
            add_edge(a, b, _open_cost(pos[a], pos[b], polygon))

    best: dict[str, float] = {source: 0.0}
    prev: dict[str, str] = {}
    done: set[str] = set()
    while True:
        current = None
        for key, distance in best.items():
            if key not in done and (current is None or distance < best[current]):
                current = key
        if current is None:
            return None
        if current == target:
            break
        done.add(current)
        for neighbour, weight in adj.get(current, []):
            candidate = best[current] + weight
            if neighbour not in best or candidate < best[neighbour]:
                best[neighbour] = candidate
                prev[neighbour] = current
    keys = [target]
    while keys[0] != source:
        before = prev.get(keys[0])
        if before is None:
            return None
        keys.insert(0, before)
    via = keys[1:-1]
    if not via:
        return None
    return [start, *(pos[key] for key in via), end]


def route_cable(
    start: Point,
    end: Point,
    cableways: list[list[Point]],
    route: dict[str, Any],
    audience: list[Point],
    tray_factor: float = CABLEWAY_TRAVEL,
) -> tuple[list[Point], str]:
    if route.get("mode") == "manual":
        waypoints = [(float(x), float(y)) for x, y in route.get("waypoints") or []]
        return [start, *waypoints, end], "manual"
    routed = _auto_route(start, end, cableways, audience, tray_factor)
    if routed is not None:
        return routed, "auto"
    return [start, end], "direct"


def _centres(elements: list[Any]) -> tuple[dict[str, Point], dict[str, Point]]:
    centre_of_element: dict[str, Point] = {}
    centre_of_device: dict[str, Point] = {}
    for element in elements:
        centre = element_centre(element)
        centre_of_element[str(element.id)] = centre
        if (
            element.linked_device_id
            and element.element_type not in SPEAKER_TYPES
            and str(element.linked_device_id) not in centre_of_device
        ):
            centre_of_device[str(element.linked_device_id)] = centre
    return centre_of_element, centre_of_device


def _route_cables(
    cables: list[Cable],
    *,
    cable_plan: dict[str, Any] | None,
    centre_of_element: dict[str, Point],
    centre_of_device: dict[str, Point],
    audience: list[Any],
    stage_offset: Point,
) -> list[dict[str, Any]]:
    plan = cable_plan or {}
    cableways = [
        [(float(x), float(y)) for x, y in way.get("points", [])]
        for way in plan.get("cableways", []) or []
    ]
    routes = plan.get("routes") or {}
    settings = plan.get("settings") or {}
    tray_factor = float(settings.get("cableway_factor") or CABLEWAY_TRAVEL)
    audience_local = [
        (float(x) - stage_offset[0], float(y) - stage_offset[1]) for x, y in audience or []
    ]
    paths = []
    for cable in cables:
        route = routes.get(cable.key) or {}
        if route.get("hidden"):
            continue
        if cable.from_element_id:
            start = centre_of_element.get(cable.from_element_id)
        else:
            start = centre_of_device.get(cable.from_device_id or "")
        if cable.to_element_id:
            end = centre_of_element.get(cable.to_element_id)
        else:
            end = centre_of_device.get(cable.to_device_id or "")
        if start is None or end is None:
            continue
        points, mode = route_cable(start, end, cableways, route, audience_local, tray_factor)
        paths.append({"key": cable.key, "points": points, "mode": mode})
    return paths


def routed_cable_paths(
    *,
    cable_plan: dict[str, Any] | None,
    channel_lists: list[Any],
    elements: list[Any],
    video_lists: list[Any],
    audience: list[Any],
    stage_offset: Point,
) -> list[dict[str, Any]]:
    """Routed cables in stage coordinates, skipping hidden and unplaced cables."""
    centre_of_element, centre_of_device = _centres(elements)
    return _route_cables(
        derive_cables(channel_lists, elements, video_lists),
        cable_plan=cable_plan,
        centre_of_element=centre_of_element,
        centre_of_device=centre_of_device,
        audience=audience,
        stage_offset=stage_offset,
    )


VIRTUAL_KINDS = {
    "channel",
    "output",
    "video_input",
    "video_destination",
    "video_list",
    "rigging_point",
    "channel_list",
}
LEGACY_KEY_TABLES = {
    "channel_patch_points",
    "output_patch_points",
    "video_patch_points",
    "video_output_patch_points",
}


def _cable_key(edge: Any) -> str:
    """Keep the legacy patch point id as the key so saved cable routes keep matching."""
    attrs = edge.attributes or {}
    table, _, legacy_id = (attrs.get("legacy_ref") or "").partition(":")
    if table == "channel_patch_points" and attrs.get("cable_point_id"):
        return str(attrs["cable_point_id"])
    if table in LEGACY_KEY_TABLES and legacy_id:
        return legacy_id
    # video connections live only on the graph: their point id is the key (the legacy point id for
    # connections that came from the tables)
    if edge.signal == "video" and attrs.get("point_id"):
        return str(attrs["point_id"])
    return str(edge.id)


class _ElementView:
    """A plot element node seen the way the legacy element row is: type, size, centre."""

    def __init__(self, node: Any, links: dict[str, Any]) -> None:
        attrs = node.attributes or {}
        self.node_id = str(node.id)
        self.legacy_id = _legacy_id(node)
        self.element_type = attrs.get("element_type") or ""
        self.label = attrs.get("label") or ""
        self.position_x = node.canvas_x_cm or 0
        self.position_y = node.canvas_y_cm or 0
        self.rotation = node.canvas_rotation or 0
        self.width_cm = attrs.get("width_cm") or 0
        self.height_cm = attrs.get("height_cm") or 0
        self.links = links


def _legacy_id(node: Any) -> str:
    """The element's public id (``graph/ids.py``): ``attributes.legacy_id`` or the legacy ref's id
    for an element imported from the old table, else its node id."""
    raw = (getattr(node, "attributes", None) or {}).get("legacy_id")
    if not raw:
        table, _, raw = (getattr(node, "legacy_ref", None) or "").partition(":")
        raw = raw if table == "stage_plot_elements" else None
    return str(raw or node.id)


def _element_views(devices: list[Any], edges: list[Any]) -> list[_ElementView]:
    links: dict[str, dict[str, Any]] = {}
    for edge in edges:
        if edge.signal == "link":
            links.setdefault(str(edge.src_device_id), {})[(edge.attributes or {}).get("role")] = (
                str(edge.dst_device_id)
            )
    nodes = sorted(
        (d for d in devices if d.kind == "plot_element"),
        key=lambda d: (str(d.created_at), str(d.id)),
    )
    return [_ElementView(n, links.get(str(n.id), {})) for n in nodes]


def derive_cables_from_graph(devices: list[Any], edges: list[Any]) -> list[Cable]:
    """Same cables as ``derive_cables``, read from the graph.

    Audio and video edges between real devices become cables. Channel and video-input nodes
    are replaced by the plot element nodes linked to them, and an output bus is looked through
    so the cable runs from the console to the next device.
    """
    by_id = {str(d.id): d for d in devices}
    elements = _element_views(devices, edges)
    into: dict[str, list[Any]] = {}
    for edge in edges:
        into.setdefault(str(edge.dst_device_id), []).append(edge)
    cables: list[Cable] = []
    for channel in (d for d in devices if d.kind == "channel"):
        points = sorted(
            (
                edge
                for edge in edges
                if (edge.attributes or {}).get("chain") == str(channel.id)
                and (edge.attributes or {}).get("point_id")
            ),
            key=lambda edge: (edge.attributes or {}).get("position") or 0,
        )
        if not points or str(points[0].src_device_id) == str(channel.id):
            # Before the channel endpoint change, the first point edge itself started at the
            # channel and emitted this source cable in the main loop below.
            continue
        linked = [e for e in elements if e.links.get("channel") == str(channel.id)]
        mics = [e for e in linked if e.element_type in MIC_TYPES]
        linked = mics or [e for e in linked if e.element_type == "performer"]
        cables.extend(
            Cable(
                key=f"src:{element.legacy_id}",
                from_element_id=element.node_id,
                to_device_id=str(points[0].src_device_id),
            )
            for element in linked
        )
    for edge in sorted(edges, key=lambda e: str(e.id)):
        if edge.signal not in ("audio", "video"):
            continue
        edge_attrs = edge.attributes or {}
        if edge_attrs.get("channel_source"):
            linked = [
                element
                for element in elements
                if element.links.get("channel") == str(edge_attrs.get("channel_id"))
            ]
            if any(element.element_type in MIC_TYPES for element in linked) or any(
                element.element_type == "performer" for element in linked
            ):
                # The plot element already represents this source at its stage position.
                continue
        src, dst = by_id.get(str(edge.src_device_id)), by_id.get(str(edge.dst_device_id))
        if src is None or dst is None or dst.kind in VIRTUAL_KINDS:
            continue
        if src.kind in ("channel", "video_input"):
            linked = [e for e in elements if e.links.get(src.kind) == str(src.id)]
            if src.kind == "channel":
                mics = [e for e in linked if e.element_type in MIC_TYPES]
                linked = mics or [e for e in linked if e.element_type == "performer"]
            else:
                linked = [e for e in linked if e.element_type != "projector"]
            cables.extend(
                Cable(key=f"src:{e.legacy_id}", from_element_id=e.node_id, to_device_id=str(dst.id))
                for e in linked
            )
        elif src.kind == "output":
            for feeder in into.get(str(src.id), []):
                origin = by_id.get(str(feeder.src_device_id))
                if origin is not None and origin.kind not in VIRTUAL_KINDS and origin.id != dst.id:
                    cables.append(
                        Cable(
                            key=_cable_key(edge),
                            from_device_id=str(origin.id),
                            to_device_id=str(dst.id),
                        )
                    )
        elif src.kind not in VIRTUAL_KINDS and src.id != dst.id:
            cables.append(
                Cable(key=_cable_key(edge), from_device_id=str(src.id), to_device_id=str(dst.id))
            )
    for element in elements:
        point_device = element.links.get("output_point")
        if element.element_type in SPEAKER_TYPES and point_device:
            cables.append(
                Cable(
                    key=f"spk:{element.legacy_id}",
                    from_device_id=point_device,
                    to_element_id=element.node_id,
                )
            )
    return cables


def _graph_centres(
    devices: list[Any], edges: list[Any]
) -> tuple[dict[str, Point], dict[str, Point]]:
    centre_of_element: dict[str, Point] = {}
    centre_of_device: dict[str, Point] = {}
    for element in _element_views(devices, edges):
        centre = element_centre(element)
        centre_of_element[element.node_id] = centre
        device_id = element.links.get("device")
        if (
            device_id
            and element.element_type not in SPEAKER_TYPES
            and device_id not in centre_of_device
        ):
            centre_of_device[device_id] = centre
    return centre_of_element, centre_of_device


def routed_cable_paths_from_graph(
    *,
    cable_plan: dict[str, Any] | None,
    devices: list[Any],
    edges: list[Any],
    audience: list[Any],
    stage_offset: Point,
) -> list[dict[str, Any]]:
    centre_of_element, centre_of_device = _graph_centres(devices, edges)
    return _route_cables(
        derive_cables_from_graph(devices, edges),
        cable_plan=cable_plan,
        centre_of_element=centre_of_element,
        centre_of_device=centre_of_device,
        audience=audience,
        stage_offset=stage_offset,
    )
