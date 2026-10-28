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


def throw_angle_deg(throw_ratio: float | None) -> float | None:
    if not throw_ratio:
        return None
    return math.degrees(2 * math.atan(1 / (2 * throw_ratio)))


def projector_ends(throw_min: float | None, throw_max: float | None) -> list[dict[str, Any]]:
    """The shortest throw (widest, filled) and, for a zoom, the longest (outline)."""
    if not throw_min:
        return []
    ends = [{"throw_ratio": throw_min, "filled": True}]
    if throw_max and throw_max > throw_min:
        ends.append({"throw_ratio": throw_max, "filled": False})
    return ends


def projection_geometry(
    apex: Point,
    screen_centre: Point,
    screen_rotation_deg: float,
    throw_ratio: float,
) -> dict[str, Any]:
    """Triangle from the projector to a screen face. The image width is distance / throw ratio."""
    theta = math.radians(screen_rotation_deg)
    u = (math.cos(theta), math.sin(theta))
    distance = math.hypot(screen_centre[0] - apex[0], screen_centre[1] - apex[1])
    image_width = distance / throw_ratio
    half = image_width / 2
    left = (screen_centre[0] - u[0] * half, screen_centre[1] - u[1] * half)
    right = (screen_centre[0] + u[0] * half, screen_centre[1] + u[1] * half)
    return {
        "image_width_cm": image_width,
        "distance_cm": distance,
        "cone": [apex, left, right],
        "zone": [left, right],
    }


def nearest_screen(
    projector: Any, elements: list[Any], throw_ratio_min: float | None
) -> Any | None:
    """The nearest screen inside the projector's throw angle (the widest throw).

    A screen outside that angle is not its target, and a projector facing the wall has none.
    """
    angle = throw_angle_deg(throw_ratio_min)
    if angle is None:
        return None
    cos_half = math.cos(math.radians(angle) / 2)
    best = None
    best_distance = math.inf
    px, py = element_centre(projector)
    theta = math.radians(float(projector.rotation or 0))
    facing = (math.sin(theta), -math.cos(theta))
    for element in elements:
        if element.element_type != "screen":
            continue
        sx, sy = element_centre(element)
        dx = sx - px
        dy = sy - py
        distance = math.hypot(dx, dy)
        if distance == 0 or (dx * facing[0] + dy * facing[1]) / distance < cos_half:
            continue
        if distance < best_distance:
            best = element
            best_distance = distance
    return best
