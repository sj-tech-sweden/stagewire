"""Weight loading per rigging point (trusses and hanging points).

Pure function over plain values. A load is one unit placed on the plot or patched as a
fixture; its weight comes from the device (Stockwire first, then the value entered).
Power is evaluated on the tree in power_tree.py.
"""

from dataclasses import dataclass


@dataclass(frozen=True)
class WeightLoad:
    label: str
    weight_kg: float | None
    rigging_point_id: str | None


def _round(value: float, places: int = 2) -> float:
    return round(value, places)


def summarize_weights(points: list[dict], loads: list[WeightLoad]) -> list[dict]:
    rows = []
    for point in points:
        hung = [load for load in loads if load.rigging_point_id == str(point["id"])]
        total = sum(load.weight_kg or 0.0 for load in hung)
        capacity = point.get("weight_capacity_kg")
        rows.append(
            {
                **point,
                "load_kg": _round(total),
                "percent": _round(total / capacity * 100, 1) if capacity else None,
                "over": bool(capacity) and total > capacity,
                "loads": [load.label for load in hung],
            }
        )
    return rows
