"""Basic 2D speaker coverage on a rasterised venue grid.

Geometry is expressed in centimetres. Plot elements are stored relative to the
stage origin, so a speaker's venue position is its stage-local position plus the
job's stage offset. Rotation follows the stage plot canvas: elements rotate about
their top-left corner, and a speaker at rotation 0 faces up (towards -y).
"""

import math
from dataclasses import dataclass

SPEAKER_TYPES = frozenset({"speaker", "speaker_main", "speaker_sub", "speaker_delay"})


@dataclass(frozen=True)
class SpeakerSector:
    apex_x: float
    apex_y: float
    front_x: float
    front_y: float
    radius_cm: float
    half_angle_rad: float


def sector_for(element: dict, stage_x_cm: float, stage_y_cm: float) -> SpeakerSector | None:
    if element.get("element_type") not in SPEAKER_TYPES:
        return None
    angle_deg = float(element.get("coverage_angle_h") or 0)
    distance_m = float(element.get("coverage_distance_m") or 0)
    if angle_deg <= 0 or distance_m <= 0:
        return None

    theta = math.radians(float(element.get("rotation") or 0))
    cos_t, sin_t = math.cos(theta), math.sin(theta)
    half_w = float(element.get("width_cm") or 0) / 2
    half_h = float(element.get("height_cm") or 0) / 2
    centre_dx = half_w * cos_t - half_h * sin_t
    centre_dy = half_w * sin_t + half_h * cos_t
    apex_x = float(element.get("position_x") or 0) + centre_dx + stage_x_cm
    apex_y = float(element.get("position_y") or 0) + centre_dy + stage_y_cm

    return SpeakerSector(
        apex_x=apex_x,
        apex_y=apex_y,
        front_x=sin_t,
        front_y=-cos_t,
        radius_cm=distance_m * 100,
        half_angle_rad=min(math.radians(angle_deg), 2 * math.pi) / 2,
    )


def _covers(sector: SpeakerSector, x: float, y: float) -> bool:
    dx = x - sector.apex_x
    dy = y - sector.apex_y
    dist_sq = dx * dx + dy * dy
    if dist_sq > sector.radius_cm * sector.radius_cm:
        return False
    if sector.half_angle_rad >= math.pi or dist_sq == 0:
        return True
    cos_angle = (dx * sector.front_x + dy * sector.front_y) / math.sqrt(dist_sq)
    return cos_angle >= math.cos(sector.half_angle_rad) - 1e-9


def coverage_grid(
    venue_width_cm: float,
    venue_height_cm: float,
    sectors: list[SpeakerSector],
    cell_cm: float,
) -> dict:
    cols = math.ceil(venue_width_cm / cell_cm) if venue_width_cm > 0 else 0
    rows = math.ceil(venue_height_cm / cell_cm) if venue_height_cm > 0 else 0
    grid: list[str] = []
    covered = 0
    for r in range(rows):
        y = (r + 0.5) * cell_cm
        line = []
        for c in range(cols):
            x = (c + 0.5) * cell_cm
            hit = any(_covers(s, x, y) for s in sectors)
            line.append("1" if hit else "0")
            covered += hit
        grid.append("".join(line))
    total = cols * rows
    return {
        "cell_cm": cell_cm,
        "cols": cols,
        "rows": rows,
        "grid": grid,
        "covered_pct": round(covered / total * 100, 1) if total else 0,
        "speaker_count": len(sectors),
    }
