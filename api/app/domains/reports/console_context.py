"""Rows for the two console reports built from the same job graph (spec §9).

- **Stage patch sheet** (stage / patch techs): ordered by the physical socket a source is plugged
  into (``AR2412 In 1``, ``AR2412 In 2``, ...), so a tech can patch straight down the page.
- **Console DSP & fader sheet** (FOH / monitor engineers): ordered by DSP strip number, with the
  label, ``+48V``, stereo link and where the strip sits on the surface.

Both read the same channel nodes; the difference is only the sort key and the columns. Pure
functions over the graph's device rows so they are unit-testable without a database.
"""

from typing import Any

from app.domains.audio import console
from app.domains.graph.ids import public_id


def _attrs(node: Any) -> dict:
    return node.attributes or {}


def _lists(devices: list[Any]) -> list[Any]:
    return sorted((d for d in devices if d.kind == "channel_list"), key=lambda d: d.position)


def _members(devices: list[Any], kind: str, list_node: Any) -> list[Any]:
    return [d for d in devices if d.kind == kind and _attrs(d).get("list_id") == str(list_node.id)]


def _number(node: Any) -> int:
    return int(_attrs(node).get("channel_number") or node.position or 0)


def _socket_label(ref: dict | None, devices_by_id: dict[str, Any], direction: str) -> str:
    """``AR2412 In 3`` for a stored socket reference; a dangling one reads ``(missing device)``."""
    if not ref:
        return ""
    device = devices_by_id.get(str(ref.get("device_id")))
    name = device.name if device is not None else "(missing device)"
    return f"{name} {direction} {ref.get('socket') or 1}"


def _pair_label(number: int, linked: bool) -> str:
    return f"{number}-{number + 1}" if linked else str(number)


def stage_patch_rows(devices: list[Any]) -> list[dict]:
    """One row per physical source, sorted by (stagebox name, socket); unpatched sources last.

    A stereo pair is *two* rows: each leg is its own preamp with its own socket (possibly on another
    stagebox), so the tech patches them independently. The channel column marks the legs ``1 (L)``
    and ``2 (R)``.
    """
    by_id = {str(d.id): d for d in devices}
    rows: list[dict] = []
    for list_node in _lists(devices):
        for node in _members(devices, "channel", list_node):
            attrs = _attrs(node)
            ref = attrs.get("dsp_source")
            device = by_id.get(str(ref.get("device_id"))) if ref else None
            number = _number(node)
            leg = {"primary": "L", "secondary": "R"}.get(attrs.get("stereo_link_role") or "")
            rows.append(
                {
                    "_sort": (
                        0 if ref else 1,
                        (device.name if device is not None else "").lower(),
                        (ref or {}).get("socket") or 0,
                        number,
                    ),
                    "stagebox_socket": _socket_label(ref, by_id, "In") or "—",
                    "channel_number": f"{number} ({leg})" if leg else str(number),
                    "source_label": attrs.get("source_label") or node.name,
                    "mic_di": attrs.get("device") or attrs.get("input_type") or "",
                    "stand": attrs.get("stand_type") or "",
                    "stage_zone": attrs.get("performer_name")
                    or (attrs.get("instrument_group") or ""),
                    "list_name": list_node.name,
                    "notes": node.notes or "",
                }
            )
    rows.sort(key=lambda r: r["_sort"])
    for row in rows:
        row.pop("_sort")
    return rows


def _surface_locations(fader: dict) -> dict[str, str]:
    """Strip id -> where it sits ("Layer 1 · Left Bank · Fader 3"); several places are joined."""
    found: dict[str, list[str]] = {}
    for layer in fader.get("layers") or []:
        for bank in layer["banks"]:
            for cell in bank["strips"]:
                if cell["id"]:
                    found.setdefault(cell["id"], []).append(
                        f"Layer {layer['layer']} · {bank['label'] or bank['id']} · "
                        f"Fader {cell['fader']}"
                    )
    return {key: "; ".join(places) for key, places in found.items()}


def _signal_path(node: Any, by_id: dict[str, Any], number: int, label: str) -> str:
    """The channel's whole route as text: source -> hops (with their socket labels) -> strip."""
    attrs = _attrs(node)
    source = by_id.get(str(attrs.get("source_device_id") or ""))
    parts = [source.name if source is not None else (attrs.get("device") or "")]
    for point in sorted(attrs.get("points") or [], key=lambda p: p.get("position") or 0):
        device = by_id.get(str(point.get("device_id")))
        name = device.name if device is not None else "(missing device)"
        extra = " ".join(x for x in (point.get("patch_label"), point.get("connector")) if x)
        parts.append(f"{name} {extra}".strip() if extra else name)
    parts.append(f"Ch {label}")
    return " → ".join(p for p in parts if p)


def _endpoint_text(endpoint: dict, by_id: dict[str, Any]) -> str:
    refs = endpoint.get("refs") or []
    sides = {1: [""], 2: [" (L)", " (R)"], 3: [" (L)", " (R)", " (C)"]}.get(len(refs), [""] * 3)
    return " + ".join(
        f"{_socket_label(ref, by_id, 'Out')}{sides[i] if i < len(sides) else ''}"
        for i, ref in enumerate(refs)
    )


def console_sheet(devices: list[Any]) -> dict[str, list[dict]]:
    """Everything needed to set the console up, as the report's tables.

    - ``console_setup``: the console, its DSP inputs, bus pool use, DCAs, installed expansion;
    - ``console_dsp``: one row per DSP strip with its source, **whole signal path**, input socket,
      +48V, stereo link, direct out, DCAs, FX sends and surface position;
    - ``console_buses``: each bus with its mode, role, pool slots, the sockets it leaves from and
      its fader;
    - ``console_dcas`` and ``console_fx``: names, members and sends in words.
    A ganged stereo pair is one DSP row (its two legs' sockets are both listed).
    """
    by_id = {str(d.id): d for d in devices}
    setup: list[dict] = []
    dsp: list[dict] = []
    buses_out: list[dict] = []
    dcas_out: list[dict] = []
    fx_out: list[dict] = []
    for list_node in _lists(devices):
        attrs_l = _attrs(list_node)
        profile = console.profile_from_stored(attrs_l.get("mixer_profile"))
        channels = _members(devices, "channel", list_node)
        outputs = sorted(_members(devices, "output", list_node), key=lambda d: d.position)
        fx_list = console.effective_fx(profile, attrs_l.get("fx_config"))
        dca_config = attrs_l.get("dca_config") or {}
        bus_dicts = [
            {
                "id": str(public_id(o)),
                "name": o.name,
                "mode": _attrs(o).get("mode"),
                "role": _attrs(o).get("role"),
            }
            for o in outputs
        ]
        fader = console.fader_map(
            profile,
            [
                {
                    "id": str(public_id(c)),
                    "channel_number": _number(c),
                    "source_label": _attrs(c).get("source_label") or c.name,
                    "is_stereo_linked": bool(_attrs(c).get("is_stereo_linked")),
                    "stereo_link_role": _attrs(c).get("stereo_link_role"),
                }
                for c in channels
            ],
            bus_dicts,
            attrs_l.get("fader_layout"),
            fx_list,
            dca_config,
        )
        where = _surface_locations(fader)
        names = {str(public_id(c)): _attrs(c).get("source_label") or c.name for c in channels}
        names.update({b["id"]: b["name"] for b in bus_dicts})
        names.update({console.fx_strip_id(e["id"]): e.get("name") or e["id"] for e in fx_list})
        names.update(
            {console.fx_send_strip_id(e["id"]): f"{e.get('name') or e['id']} send" for e in fx_list}
        )
        budget = console.bus_budget(profile, bus_dicts, fx_list)

        # --- setup -------------------------------------------------------------------------
        def add(item: str, value: Any, list_name: str = list_node.name) -> None:
            if value not in (None, ""):
                setup.append({"list_name": list_name, "item": item, "value": str(value)})

        add("Console", attrs_l.get("mixer_product_name") or list_node.name)
        if profile is not None:
            add("Profile", f"{profile.name or profile.architecture} ({profile.source})")
            dsp_in = profile.dsp_inputs
            add(
                "DSP inputs",
                f"{dsp_in.mono} mono + {dsp_in.stereo} stereo + {dsp_in.fx_returns} FX returns",
            )
            if budget["enabled"]:
                add(
                    "Bus pool",
                    f"{budget['used_slots']} / {budget['total_slots']} slots used"
                    + (
                        f", {budget['fx_send_slots']} by FX sends"
                        if budget.get("fx_send_slots")
                        else ""
                    )
                    + (f"; {'; '.join(budget['violations'])}" if budget["violations"] else ""),
                )
            add("DCAs", profile.dcas or "")
        for card in attrs_l.get("expansion_installed") or []:
            add(
                "Expansion",
                f"{card['protocol']}: {card['channels_in']} in / {card['channels_out']} out",
            )
        add("Channels", len(channels))
        add("Buses", len(outputs))

        # --- inputs -------------------------------------------------------------------------
        for node in sorted(channels, key=_number):
            attrs = _attrs(node)
            if attrs.get("stereo_link_role") == "secondary":
                continue
            linked = bool(attrs.get("is_stereo_linked"))
            number = _number(node)
            label = _pair_label(number, linked)
            node_id = str(public_id(node))
            partner = None
            if linked:
                partner = next(
                    (
                        c
                        for c in channels
                        if str(public_id(c)) == str(attrs.get("stereo_partner_id"))
                    ),
                    None,
                )
            sockets = [
                x
                for x in (
                    _socket_label(attrs.get("dsp_source"), by_id, "In"),
                    _socket_label(_attrs(partner).get("dsp_source"), by_id, "In")
                    if partner is not None
                    else "",
                )
                if x
            ]
            direct = [
                x
                for x in (
                    _socket_label(attrs.get("direct_out"), by_id, "Out"),
                    _socket_label(_attrs(partner).get("direct_out"), by_id, "Out")
                    if partner is not None
                    else "",
                )
                if x
            ]
            dsp.append(
                {
                    "channel_number": label,
                    "source_label": attrs.get("source_label") or node.name,
                    "source": attrs.get("device") or attrs.get("input_type") or "",
                    "signal_path": _signal_path(node, by_id, number, label),
                    "input_socket": " / ".join(sockets),
                    # a stereo link shares +48V, so the primary speaks for the pair
                    "phantom_power": "+48V" if attrs.get("phantom_power") else "",
                    "stereo_link": f"Ch {number}+{number + 1} (stereo)" if linked else "",
                    "direct_out": " / ".join(direct),
                    "dca": ", ".join(
                        cfg.get("name") or f"DCA {n}"
                        for n, cfg in sorted(dca_config.items(), key=lambda kv: int(kv[0]))
                        if node_id in (cfg.get("members") or [])
                    ),
                    "fx_sends": ", ".join(
                        e.get("name") or e["id"]
                        for e in fx_list
                        if node_id in (e.get("sends") or [])
                    ),
                    "surface_location": where.get(node_id, ""),
                    "list_name": list_node.name,
                    "notes": node.notes or "",
                }
            )

        # --- buses --------------------------------------------------------------------------
        slots_of = {e["id"]: e for e in budget.get("entries") or []}
        for o, bus in zip(outputs, bus_dicts, strict=True):
            entry = slots_of.get(bus["id"], {})
            buses_out.append(
                {
                    "bus": o.name,
                    "mode": bus["mode"] or "mono",
                    "role": bus["role"] or "aux",
                    "slots": (
                        f"{entry.get('slot_start')}–{entry.get('slot_end')}" if entry else ""
                    ),
                    "outputs": " ; ".join(
                        _endpoint_text(e, by_id) for e in _attrs(o).get("out_endpoints") or []
                    ),
                    "surface_location": where.get(bus["id"], ""),
                    "list_name": list_node.name,
                    "notes": o.notes or "",
                }
            )

        # --- DCAs and FX --------------------------------------------------------------------
        for number, cfg in sorted(dca_config.items(), key=lambda kv: int(kv[0])):
            dcas_out.append(
                {
                    "dca": f"DCA {number}",
                    "name": cfg.get("name") or "",
                    "members": ", ".join(names.get(m, m) for m in cfg.get("members") or []),
                    "surface_location": where.get(f"dca-{number}", ""),
                    "list_name": list_node.name,
                }
            )
        for engine in fx_list:
            if not engine.get("configured", True):
                continue
            fx_out.append(
                {
                    "fx": engine.get("name") or engine["id"],
                    "type": engine.get("type") or "",
                    "return": "stereo" if engine.get("stereo_return", True) else "mono",
                    "sent_from": ", ".join(names.get(c, c) for c in engine.get("sends") or []),
                    "surface_location": "; ".join(
                        x
                        for x in (
                            where.get(console.fx_strip_id(engine["id"])),
                            where.get(console.fx_send_strip_id(engine["id"])),
                        )
                        if x
                    ),
                    "list_name": list_node.name,
                }
            )
    return {
        "console_setup": setup,
        "console_dsp": dsp,
        "console_buses": buses_out,
        "console_dcas": dcas_out,
        "console_fx": fx_out,
    }


def dsp_rows(devices: list[Any]) -> list[dict]:
    """The DSP channel rows only (kept for callers and tests that read just the strips)."""
    return console_sheet(devices)["console_dsp"]
