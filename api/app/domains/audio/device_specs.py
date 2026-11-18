"""Device input and output counts, taken from a device's Stockwire product.

Field contract (Stockwire product ``specs`` object, all optional):
- ``inputs``: number of inputs.
- ``outputs``: number of outputs.
- ``connectors``: the connectors of the product. Either a list of names, for example
  ``["sdi", "hdmi"]`` (each counts as one bidirectional connector), or a list of groups
  ``{"connector": "xlr3", "direction": "in" | "out" | "both", "count": 8, "signal": "audio"}``
  (``count`` defaults to 1, ``signal`` is optional). Names are the Stagewire connector kinds
  (xlr3, xlr5, trs, speakon, dante, dsnake, aes50, madi, avb, ethernet, ethercon, fiber, sdi, hdmi,
  displayport, bnc, usb, dmx, powercon, schuko, cee16) or any text; an unknown name is kept as
  typed and joins the shared connector list when imported.

  In addition to the explicit ``connectors`` list, ``specs.mixer.expansion_ports`` and
  ``specs.stagebox.digital_io`` describe structured digital links (dSnake / Dante / AES50 /
  AVB / MADI) carrying separate input/output channel counts; each link is expanded into an
  ``in`` and/or ``out`` connector group whose ``connector`` is the protocol, so an imported
  mixer or stagebox actually gains those sockets.
- ``power_inlet``: how the product takes mains (``iec_c13``, ``attached_schuko``, ``powercon``,
  ``cee16`` or ``other``).

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


DIRECTIONS = {
    "in": "in",
    "input": "in",
    "out": "out",
    "output": "out",
    "both": "both",
    "io": "both",
    "bidirectional": "both",
}
SIGNALS = {"audio", "video", "dmx", "power", "data"}


def _expansion_connector_groups(ports: Any, in_key: str, out_key: str) -> list[dict]:
    """Turn structured digital links into connector groups.

    Both a mixer's ``expansion_ports`` (keys ``max_channels_in`` / ``max_channels_out``) and a
    stagebox's ``digital_io`` (keys ``channels_in`` / ``channels_out``) describe a digital
    transport (dSnake / Dante / AES50 / AVB / MADI) carrying separate input and output channel
    counts. Each becomes an ``in`` group and/or an ``out`` group whose ``connector`` is the
    protocol, so an imported device actually gains those sockets (and the soft patch surfaces
    them). Ports without a protocol, or with no channel count on a side, are skipped.
    """
    if not isinstance(ports, list):
        return []
    groups: list[dict] = []
    for port in ports:
        if not isinstance(port, dict):
            continue
        protocol = str(port.get("protocol") or "").strip().lower()
        if not protocol:
            continue
        ch_in = _count(port.get(in_key))
        ch_out = _count(port.get(out_key))
        if ch_in:
            groups.append(
                {"connector": protocol, "direction": "in", "count": ch_in, "signal": "audio"}
            )
        if ch_out:
            groups.append(
                {"connector": protocol, "direction": "out", "count": ch_out, "signal": "audio"}
            )
    return groups


def _mixer_expansion_connector_groups(specs: dict) -> list[dict]:
    mixer = specs.get("mixer")
    if not isinstance(mixer, dict):
        return []
    return _expansion_connector_groups(
        mixer.get("expansion_ports"), "max_channels_in", "max_channels_out"
    )


def _stagebox_digital_connector_groups(specs: dict) -> list[dict]:
    stagebox = specs.get("stagebox")
    if not isinstance(stagebox, dict):
        return []
    return _expansion_connector_groups(stagebox.get("digital_io"), "channels_in", "channels_out")


def product_connector_groups(product: dict | None) -> list[dict]:
    """The product's connectors as ``{connector, direction, count, signal}`` groups.

    Reads both forms of ``specs.connectors`` (see the module docstring). Entries that name no
    connector are dropped; an unknown direction counts as ``both`` and a bad count as 1. On top
    of the explicit ``connectors`` list, the structured ``specs.mixer.expansion_ports`` and
    ``specs.stagebox.digital_io`` digital links are expanded into real input/output sockets.
    """
    specs = (product or {}).get("specs") or {}
    groups: list[dict] = []
    raw = specs.get("connectors")
    if isinstance(raw, list):
        for entry in raw:
            if isinstance(entry, str):
                entry = {"connector": entry}
            if not isinstance(entry, dict):
                continue
            name = str(
                entry.get("connector") or entry.get("type") or entry.get("name") or ""
            ).strip()
            if not name:
                continue
            signal = str(entry.get("signal") or "").lower()
            groups.append(
                {
                    "connector": name.lower(),
                    "direction": DIRECTIONS.get(str(entry.get("direction") or "").lower(), "both"),
                    "count": _count(entry.get("count")) or 1,
                    "signal": signal if signal in SIGNALS else None,
                }
            )
    # Structured digital links become real sockets on import.
    groups.extend(_mixer_expansion_connector_groups(specs))
    groups.extend(_stagebox_digital_connector_groups(specs))
    return groups


def product_io_specs(product: dict | None) -> dict:
    specs = (product or {}).get("specs") or {}
    groups = product_connector_groups(product)
    return {
        "inputs": _count(specs.get("inputs")),
        "outputs": _count(specs.get("outputs")),
        "connectors": [g["connector"] for g in groups],
        "connector_groups": groups,
        "power_inlet": str(specs.get("power_inlet") or "").strip().lower() or None,
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
