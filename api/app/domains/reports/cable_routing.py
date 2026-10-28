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
            for previous, current in zip(points, points[1:], strict=False):
                if previous.device_id != current.device_id:
                    cables.append(
                        Cable(
                            key=str(current.id),
                            from_device_id=str(previous.device_id),
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
    centre_of_element, centre_of_device = _centres(elements)
    paths = []
    for cable in derive_cables(channel_lists, elements, video_lists):
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
