"""Fixture type values from a Stockwire product.

Field contract (all optional):
- ``name``, ``manufacturer``: the fixture type's name and maker.
- ``weight_kg`` (top level): weight of one unit, a decimal string or number.
- ``power_consumption_watts`` (top level): power draw of one unit.
- ``specs.lt_fixture_type``: the fixture category, for example ``PAR``.
- ``specs.channel_modes``: list of ``{"name", "footprint"}``, one per DMX mode.
"""

from typing import Any


def _positive(value: Any) -> float | None:
    if value is None:
        return None
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return number if number > 0 else None


def _modes(value: Any) -> list[dict]:
    if not isinstance(value, list):
        return []
    modes = []
    for item in value:
        if not isinstance(item, dict):
            continue
        name = str(item.get("name") or "").strip()
        try:
            footprint = int(item.get("footprint"))
        except (TypeError, ValueError):
            continue
        if name and 1 <= footprint <= 512:
            modes.append({"name": name, "footprint": footprint})
    return modes


def type_from_product(product: dict) -> dict:
    specs = product.get("specs") or {}
    return {
        "name": str(product.get("name") or "").strip(),
        "manufacturer": str(product.get("manufacturer") or product.get("brand") or "").strip(),
        "category": str(specs.get("lt_fixture_type") or "").strip(),
        "weight_kg": _positive(product.get("weight_kg")),
        "power_watts": _positive(product.get("power_consumption_watts")),
        "modes": _modes(specs.get("channel_modes")),
    }
