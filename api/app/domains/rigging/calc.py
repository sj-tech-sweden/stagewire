"""Weight loading per rigging point and power per distro circuit and phase.

Pure functions over plain values, so they are tested without a database. A load is one
unit placed on the plot or patched as a fixture. Its weight and power come from the
device (Stockwire first, then the value entered), and it may be hung on a rigging point
and/or fed from a power circuit.
"""

from dataclasses import dataclass

PHASES = ("L1", "L2", "L3")


@dataclass(frozen=True)
class Load:
    id: str
    kind: str
    label: str
    weight_kg: float | None
    power_w: float | None
    rigging_point_id: str | None
    power_circuit_id: str | None


def _round(value: float, places: int = 1) -> float:
    return round(value, places)


def summarize(
    points: list[dict], distros: list[dict], circuits: list[dict], loads: list[Load]
) -> dict:
    point_rows = []
    for point in points:
        hung = [load for load in loads if load.rigging_point_id == str(point["id"])]
        total = sum(load.weight_kg or 0.0 for load in hung)
        capacity = point.get("weight_capacity_kg")
        point_rows.append(
            {
                **point,
                "load_kg": _round(total, 2),
                "percent": _round(total / capacity * 100) if capacity else None,
                "over": bool(capacity) and total > capacity,
                "loads": [load.label for load in hung],
            }
        )

    distro_rows = []
    for distro in distros:
        volts = distro.get("voltage") or 230
        own = [circuit for circuit in circuits if str(circuit["distro_id"]) == str(distro["id"])]
        phase_watts = dict.fromkeys(PHASES, 0.0)
        circuit_rows = []
        for circuit in own:
            fed = [load for load in loads if load.power_circuit_id == str(circuit["id"])]
            watts = sum(load.power_w or 0.0 for load in fed)
            amps = watts / volts
            breaker = circuit.get("breaker_amps")
            phase_watts[circuit["phase"]] += watts
            circuit_rows.append(
                {
                    **circuit,
                    "watts": _round(watts),
                    "amps": _round(amps, 2),
                    "over": bool(breaker) and amps > breaker,
                    "loads": [load.label for load in fed],
                }
            )
        capacity = distro.get("amps_per_phase")
        phases = {}
        for phase in PHASES:
            amps = phase_watts[phase] / volts
            phases[phase] = {
                "watts": _round(phase_watts[phase]),
                "amps": _round(amps, 2),
                "capacity_amps": capacity,
                "over": bool(capacity) and amps > capacity,
            }
        amps_values = [phases[phase]["amps"] for phase in PHASES]
        high = max(amps_values)
        imbalance = _round((high - min(amps_values)) / high * 100) if high > 0 else 0.0
        distro_rows.append(
            {
                **distro,
                "phases": phases,
                "imbalance_pct": imbalance,
                "circuits": circuit_rows,
            }
        )

    return {
        "points": point_rows,
        "distros": distro_rows,
        "unassigned_weight": [
            load.label for load in loads if load.weight_kg and not load.rigging_point_id
        ],
        "unassigned_power": [
            load.label for load in loads if load.power_w and not load.power_circuit_id
        ],
    }
