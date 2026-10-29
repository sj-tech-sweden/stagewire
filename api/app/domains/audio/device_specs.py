"""Device input and output counts, taken from a device's Stockwire product.

Field contract (Stockwire product ``specs`` object, all optional):
- ``inputs``: number of inputs.
- ``outputs``: number of outputs.
- ``connectors``: list of connector names, for example ``["sdi", "hdmi"]``.

A manual override on the device wins, then these values, then the patch list.
"""

from collections.abc import Awaitable, Callable
from typing import Any

ProductFetcher = Callable[[str], Awaitable[dict | None]]


def _count(value: Any) -> int | None:
    if value is None:
        return None
    try:
        number = int(value)
    except (TypeError, ValueError):
        return None
    return number if number >= 0 else None


def product_io_specs(product: dict | None) -> dict:
    specs = (product or {}).get("specs") or {}
    connectors = specs.get("connectors") or []
    return {
        "inputs": _count(specs.get("inputs")),
        "outputs": _count(specs.get("outputs")),
        "connectors": [str(c) for c in connectors if c] if isinstance(connectors, list) else [],
    }


def _positive(value: Any) -> float | None:
    if value is None:
        return None
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return number if number > 0 else None


def product_physical_specs(product: dict | None) -> dict:
    """Weight and power are top-level product fields in Stockwire, not under ``specs``."""
    product = product or {}
    return {
        "weight_kg": _positive(product.get("weight_kg")),
        "power_watts": _positive(product.get("power_consumption_watts")),
    }


def effective_value(
    stockwire: float | None, manual: float | None
) -> tuple[float | None, str | None]:
    """Stockwire wins over the value entered on the device; the source says which."""
    if stockwire is not None:
        return stockwire, "stockwire"
    if manual is not None:
        return manual, "manual"
    return None, None


async def resolve_device_physical(
    device_product: dict[str, str],
    fetch_product: ProductFetcher | None,
) -> dict[str, dict]:
    """Stockwire weight and power for each device that has a product, keyed by device id."""
    if fetch_product is None:
        return {}
    cache: dict[str, dict] = {}
    result: dict[str, dict] = {}
    for device_id, product_id in device_product.items():
        if product_id not in cache:
            try:
                product = await fetch_product(product_id)
            except Exception:
                product = None
            cache[product_id] = product_physical_specs(product)
        result[device_id] = cache[product_id]
    return result


async def resolve_device_io(
    device_product: dict[str, str],
    fetch_product: ProductFetcher | None,
) -> dict[str, dict]:
    """Stockwire I/O data for each device that has a product, keyed by device id."""
    if fetch_product is None:
        return {}
    cache: dict[str, dict] = {}
    result: dict[str, dict] = {}
    for device_id, product_id in device_product.items():
        if product_id not in cache:
            try:
                product = await fetch_product(product_id)
            except Exception:
                product = None
            cache[product_id] = product_io_specs(product)
        result[device_id] = cache[product_id]
    return result
