"""Camera and projector geometry for stage-plot reports.

Mirrors web/src/utils/camera.js and web/src/utils/projection.js so a report draws the
same views as the stage plot. Units are cm for plan geometry and m for distances.
"""

import math
from typing import Any

from app.domains.reports.cable_routing import Point, element_centre

IMAGE_ASPECT = 16 / 9
FIXED_LENS_TOLERANCE = 0.05


def horizontal_fov_deg(sensor_width_mm: float | None, focal_mm: float | None) -> float | None:
    if not sensor_width_mm or not focal_mm:
        return None
    return 2 * math.degrees(math.atan(sensor_width_mm / (2 * focal_mm)))


def coverage_focals(
    focal_min_mm: float | None,
    focal_max_mm: float | None,
    mode: str = "range",
    chosen_mm: float | None = None,
) -> list[dict[str, Any]]:
    """Focal lengths to draw. 'filled' is the widest end; the other end is an outline."""
    if not focal_min_mm:
        return []
    if mode == "chosen":
        return [{"focal_mm": chosen_mm or focal_min_mm, "filled": True}]
    ends = [{"focal_mm": focal_min_mm, "filled": True}]
    if focal_max_mm and focal_max_mm > focal_min_mm:
        ends.append({"focal_mm": focal_max_mm, "filled": False})
    return ends


def _exit_distance(origin: Point, direction: Point, box: dict[str, float]) -> float:
    t = math.inf
    if direction[0] > 1e-9:
        t = min(t, (box["maxX"] - origin[0]) / direction[0])
    if direction[0] < -1e-9:
        t = min(t, (box["minX"] - origin[0]) / direction[0])
    if direction[1] > 1e-9:
        t = min(t, (box["maxY"] - origin[1]) / direction[1])
    if direction[1] < -1e-9:
        t = min(t, (box["minY"] - origin[1]) / direction[1])
    return max(0.0, t)


def view_polygon(
    apex: Point,
    rotation_deg: float,
    fov_deg: float,
    box: dict[str, float],
    max_distance_cm: float | None = None,
    steps: int = 48,
) -> list[Point]:
    """A fan of rays across the field of view, each ending at the wall or the max distance."""
    theta = math.radians(rotation_deg)
    base = math.atan2(-math.cos(theta), math.sin(theta))
    half = math.radians(fov_deg or 0) / 2
    points = [apex]
    for step in range(steps + 1):
        angle = base - half + 2 * half * step / steps
        direction = (math.cos(angle), math.sin(angle))
        reach = _exit_distance(apex, direction, box)
        if max_distance_cm:
            reach = min(reach, max_distance_cm)
        points.append((apex[0] + direction[0] * reach, apex[1] + direction[1] * reach))
    return points


def fill_distance_range(
    throw_min: float | None,
    throw_max: float | None,
    screen_width_cm: float | None,
    screen_height_cm: float | None,
    aspect: float = IMAGE_ASPECT,
) -> tuple[float, float] | None:
    """Distances (m) at which the projector fills the screen, from its throw ratio range."""
    if not throw_min or not screen_width_cm:
        return None
    limit_cm = (
        min(screen_width_cm, screen_height_cm * aspect) if screen_height_cm else screen_width_cm
    )
    width_m = limit_cm / 100
    high = throw_max or throw_min
    return throw_min * width_m, high * width_m


def fit_status(distance_m: float | None, fill_range: tuple[float, float] | None) -> str | None:
    if fill_range is None or distance_m is None:
        return None
    low, high = fill_range
    fixed = high - low < 1e-6
    lower = low * (1 - FIXED_LENS_TOLERANCE) if fixed else low
    upper = high * (1 + FIXED_LENS_TOLERANCE) if fixed else high
    if distance_m < lower:
        return "close"
    if distance_m > upper:
        return "far"
    return "fits"


def projection_geometry(
    apex: Point,
    screen_centre: Point,
    screen_rotation_deg: float,
    screen_width_cm: float,
    screen_height_cm: float,
    aspect: float = IMAGE_ASPECT,
) -> dict[str, Any]:
    """The image sits on the screen face that points at the projector."""
    theta = math.radians(screen_rotation_deg)
    u = (math.cos(theta), math.sin(theta))
    n = (math.sin(theta), -math.cos(theta))
    towards = n[0] * (apex[0] - screen_centre[0]) + n[1] * (apex[1] - screen_centre[1])
    side = -1 if towards < 0 else 1
    depth = (screen_height_cm or 0) / 2
    face = (
        screen_centre[0] + side * n[0] * depth,
        screen_centre[1] + side * n[1] * depth,
    )
    limit_cm = (
        min(screen_width_cm, screen_height_cm * aspect) if screen_height_cm else screen_width_cm
    )
    half = limit_cm / 2
    left = (face[0] - u[0] * half, face[1] - u[1] * half)
    right = (face[0] + u[0] * half, face[1] + u[1] * half)
    return {
        "image_width_cm": limit_cm,
        "distance_cm": math.hypot(face[0] - apex[0], face[1] - apex[1]),
        "cone": [apex, left, right],
        "zone": [left, right],
    }


def nearest_screen(projector: Any, elements: list[Any]) -> Any | None:
    best = None
    best_distance = math.inf
    projector_centre = element_centre(projector)
    for element in elements:
        if element.element_type != "screen":
            continue
        centre = element_centre(element)
        distance = math.hypot(centre[0] - projector_centre[0], centre[1] - projector_centre[1])
        if distance < best_distance:
            best = element
            best_distance = distance
    return best
