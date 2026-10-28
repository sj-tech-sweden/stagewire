"""Camera and lens values, taken from Stockwire products when present.

Field contract (Stockwire product ``specs`` object, all optional):
- ``cam_sensor_width_mm``: sensor width in millimetres (camera products).
- ``cam_max_distance_m``: longest useful distance in metres (camera products).
- ``lens_focal_length_min_mm`` / ``lens_focal_length_max_mm``: focal range (lens or
  camera-with-lens products).

Stockwire values win over the values entered on the device. Without Stockwire, the
device values are used. A camera element may link a camera device and a lens device.
"""

from collections.abc import Awaitable, Callable, Iterable
from typing import Any

ProductFetcher = Callable[[str], Awaitable[dict | None]]


def _number(value: Any) -> float | None:
    if value is None:
        return None
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return number if number > 0 else None


def product_camera_specs(product: dict | None) -> dict[str, float]:
    specs = (product or {}).get("specs") or {}
    fields = {
        "sensor_width_mm": _number(specs.get("cam_sensor_width_mm")),
        "focal_min_mm": _number(specs.get("lens_focal_length_min_mm")),
        "focal_max_mm": _number(specs.get("lens_focal_length_max_mm")),
        "max_distance_m": _number(specs.get("cam_max_distance_m")),
    }
    return {k: v for k, v in fields.items() if v is not None}


def _pick(*candidates: dict[str, float | None]) -> dict[str, float | None]:
    """First non-empty value for each field, in priority order."""
    out: dict[str, float | None] = {}
    for field in ("sensor_width_mm", "focal_min_mm", "focal_max_mm", "max_distance_m"):
        out[field] = next((c[field] for c in candidates if c.get(field) is not None), None)
    return out


def _device_values(device: dict | None) -> dict[str, float | None]:
    device = device or {}
    return {
        "sensor_width_mm": _number(device.get("sensor_width_mm")),
        "focal_min_mm": _number(device.get("focal_min_mm")),
        "focal_max_mm": _number(device.get("focal_max_mm")),
        "max_distance_m": _number(device.get("max_distance_m")),
    }


async def resolve_camera_specs(
    elements: Iterable[dict],
    devices: dict[str, dict],
    fetch_product: ProductFetcher | None,
) -> dict[str, dict]:
    """Effective camera values for every camera element, keyed by element id.

    ``devices`` maps device id to its row: type, manual values and product id.
    """
    cache: dict[str, dict] = {}

    async def product_specs(product_id: str) -> dict[str, float]:
        if product_id not in cache:
            product = None
            if fetch_product is not None:
                try:
                    product = await fetch_product(product_id)
                except Exception:
                    product = None
            cache[product_id] = product_camera_specs(product)
        return cache[product_id]

    result: dict[str, dict] = {}
    for el in elements:
        camera = devices.get(str(el.get("linked_device_id") or ""))
        lens = devices.get(str(el.get("linked_lens_device_id") or ""))
        if camera is None and lens is None:
            continue
        camera_product = (
            await product_specs(camera["stockwire_product_id"])
            if camera and camera.get("stockwire_product_id")
            else {}
        )
        lens_product = (
            await product_specs(lens["stockwire_product_id"])
            if lens and lens.get("stockwire_product_id")
            else {}
        )
        values = _pick(
            camera_product,
            lens_product,
            _device_values(camera),
            _device_values(lens),
        )
        from_stockwire = bool(camera_product or lens_product)
        result[str(el["id"])] = {
            **values,
            "source": "stockwire" if from_stockwire else "manual",
            "focal_mm": _chosen_focal(el.get("focal_mm"), values),
        }
    return result


def _chosen_focal(chosen: Any, values: dict[str, float | None]) -> float | None:
    """The focal length in use: the element's choice if it is in range, else the widest."""
    low = values.get("focal_min_mm")
    high = values.get("focal_max_mm") or low
    if low is None:
        return None
    value = _number(chosen)
    if value is not None and low <= value <= (high or low):
        return value
    return low
