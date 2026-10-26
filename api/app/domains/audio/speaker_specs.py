"""Speaker coverage data, taken from a speaker's output device's Stockwire product.

Field contract (Stockwire product ``specs`` object, all optional):
- ``dispersion_h_deg``: horizontal coverage angle in degrees.
- ``throw_m``: throw distance in metres.

Values from the product win over the manual values on the element. A missing or
unreachable product falls back to the manual values, so the view works without
the Stockwire integration.
"""

from collections.abc import Awaitable, Callable, Iterable
from typing import Any

from app.domains.audio.coverage import SPEAKER_TYPES

ProductFetcher = Callable[[str], Awaitable[dict | None]]


def _number(value: Any) -> float | None:
    if value is None:
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def product_speaker_specs(product: dict | None) -> dict[str, float]:
    specs = (product or {}).get("specs") or {}
    out: dict[str, float] = {}
    angle = _number(specs.get("dispersion_h_deg"))
    if angle is not None:
        out["coverage_angle_h"] = angle
    distance = _number(specs.get("throw_m"))
    if distance is not None:
        out["coverage_distance_m"] = distance
    return out


async def resolve_speaker_specs(
    elements: Iterable[dict],
    point_device: dict[str, str],
    device_product: dict[str, str],
    fetch_product: ProductFetcher | None,
) -> dict[str, dict]:
    """Effective coverage values for every speaker element, keyed by element id."""
    cache: dict[str, dict | None] = {}

    async def product_for(product_id: str) -> dict | None:
        if product_id not in cache:
            try:
                cache[product_id] = await fetch_product(product_id) if fetch_product else None
            except Exception:
                cache[product_id] = None
        return cache[product_id]

    result: dict[str, dict] = {}
    for el in elements:
        if el.get("element_type") not in SPEAKER_TYPES:
            continue
        product = None
        point_id = el.get("linked_output_point_id")
        device_id = point_device.get(point_id) if point_id else None
        product_id = device_product.get(device_id) if device_id else None
        if product_id:
            product = await product_for(product_id)
        from_product = product_speaker_specs(product)
        result[el["id"]] = {
            "source": "stockwire" if from_product else "manual",
            "product_name": (product or {}).get("name") if from_product else None,
            "coverage_angle_h": from_product.get(
                "coverage_angle_h", float(el.get("coverage_angle_h") or 0)
            ),
            "coverage_distance_m": from_product.get(
                "coverage_distance_m", float(el.get("coverage_distance_m") or 0)
            ),
        }
    return result
