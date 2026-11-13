"""Digital console model: ``specs.mixer`` parsing, bus-pool budget, stereo linking, fader map.

This module is pure (no database, no HTTP) so the rules are easy to test and reuse from the
router, the report contexts and the Stockwire sync.

Where the data lives
--------------------
A channel list (graph node, kind ``channel_list``) represents one console. Its attributes carry

- ``mixer_profile``: the console's *effective profile* as stored (see ``MixerProfile``), tagged
  with ``source`` = ``stockwire`` (parsed from the product's ``specs.mixer``), ``preset`` (a
  built-in profile such as the GLD-80) or ``manual`` (typed in by the engineer);
- the legacy flat fields ``mixer_inputs`` / ``mixer_buses`` still describe a simple console.

A list with **no** profile is a *simple* console (analog desk, CQ-18T style compact digital):
flat inputs/outputs, no bus pool, no surface layers. Every function here treats ``profile is
None`` as "nothing to enforce" so such consoles keep working without any configuration.

Stockwire ``specs.mixer`` contract (all keys optional; unknown keys are ignored, bad values are
dropped rather than raised, because Stockwire data is not under our control)::

    {"architecture": "digital_bus_pool",
     "dsp_inputs": {"mono": 44, "stereo": 2, "fx_returns": 8},
     "bus_pool": {"total_slots": 30, "max_mixes": 20, "stereo_slot_cost": 2, "lcr_slot_cost": 3,
                  "allowed_roles": ["aux", "group", "matrix", "main", "fx_send"],
                  "odd_even_stereo_pairing": false},
     "dcas": 16,
     "surface": {"banks": [{"id": "A", "label": "Left Bank", "faders": 12}], "layers": 4},
     "expansion_ports": [{"protocol": "dsnake", "max_channels_in": 48, "max_channels_out": 24}]}

Manual input (``MixerProfile.model_validate``) is strict: it is the engineer's own data and a
mistake should be reported, not silently dropped.
"""

from __future__ import annotations

from collections.abc import Iterable
from typing import Any, Literal

from pydantic import BaseModel, Field, field_validator

ARCHITECTURES = ("simple", "digital_bus_pool")
BUS_ROLES = ("aux", "group", "matrix", "main", "fx_send")
BUS_MODES = ("mono", "stereo", "lcr")
SOURCES = ("stockwire", "preset", "manual")


class DspInputs(BaseModel):
    mono: int = Field(default=0, ge=0)
    stereo: int = Field(default=0, ge=0)
    fx_returns: int = Field(default=0, ge=0)


class BusPool(BaseModel):
    total_slots: int = Field(ge=0)
    max_mixes: int | None = Field(default=None, ge=0)
    stereo_slot_cost: int = Field(default=2, ge=1)
    lcr_slot_cost: int = Field(default=3, ge=1)
    allowed_roles: list[str] = Field(default_factory=lambda: list(BUS_ROLES))
    # When true a stereo/LCR bus must start on an odd slot (1, 3, 5, ...), so a mono bus in front of
    # it can leave one slot unusable. ``assign_slots`` models that waste.
    odd_even_stereo_pairing: bool = False

    @field_validator("allowed_roles")
    @classmethod
    def _roles(cls, value: list[str]) -> list[str]:
        cleaned = [str(r).strip().lower() for r in value if str(r).strip()]
        return cleaned or list(BUS_ROLES)


class Bank(BaseModel):
    id: str
    label: str = ""
    faders: int = Field(ge=0)


class Surface(BaseModel):
    banks: list[Bank] = Field(default_factory=list)
    layers: int = Field(default=1, ge=1)


class ExpansionPort(BaseModel):
    protocol: str
    slots: int | None = Field(default=None, ge=0)
    max_channels: int | None = Field(default=None, ge=0)
    max_channels_in: int | None = Field(default=None, ge=0)
    max_channels_out: int | None = Field(default=None, ge=0)


class MixerProfile(BaseModel):
    architecture: Literal["simple", "digital_bus_pool"] = "digital_bus_pool"
    dsp_inputs: DspInputs = Field(default_factory=DspInputs)
    bus_pool: BusPool | None = None
    dcas: int = Field(default=0, ge=0)
    surface: Surface | None = None
    expansion_ports: list[ExpansionPort] = Field(default_factory=list)
    # Which input strips may be linked: ``odd_even`` (1-2, 3-4, ...) is how GLD/SQ/CL pair strips;
    # ``adjacent`` allows any N / N+1.
    input_pairing: Literal["odd_even", "adjacent"] = "odd_even"
    source: Literal["stockwire", "preset", "manual"] = "manual"
    preset: str | None = None
    name: str | None = None


# --- parsing ----------------------------------------------------------------------------------


def _int(value: Any) -> int | None:
    if isinstance(value, bool) or value is None:
        return None
    try:
        number = int(value)
    except (TypeError, ValueError):
        return None
    return number if number >= 0 else None


def parse_mixer_specs(product: dict | None) -> MixerProfile | None:
    """Read ``specs.mixer`` of a Stockwire product; ``None`` when it has no usable mixer block.

    Tolerant by design: a missing/garbled field falls back to its default instead of failing, so a
    half-filled product still yields a profile the engineer can complete by hand (spec §5).
    """
    specs = (product or {}).get("specs") or {}
    raw = specs.get("mixer") if isinstance(specs, dict) else None
    if not isinstance(raw, dict) or not raw:
        return None

    dsp_raw = raw.get("dsp_inputs") if isinstance(raw.get("dsp_inputs"), dict) else {}
    dsp = DspInputs(
        mono=_int(dsp_raw.get("mono")) or 0,
        stereo=_int(dsp_raw.get("stereo")) or 0,
        fx_returns=_int(dsp_raw.get("fx_returns")) or 0,
    )

    pool: BusPool | None = None
    pool_raw = raw.get("bus_pool")
    if isinstance(pool_raw, dict) and _int(pool_raw.get("total_slots")) is not None:
        roles = pool_raw.get("allowed_roles")
        pool = BusPool(
            total_slots=_int(pool_raw.get("total_slots")) or 0,
            max_mixes=_int(pool_raw.get("max_mixes")),
            stereo_slot_cost=max(_int(pool_raw.get("stereo_slot_cost")) or 2, 1),
            lcr_slot_cost=max(_int(pool_raw.get("lcr_slot_cost")) or 3, 1),
            allowed_roles=[str(r) for r in roles] if isinstance(roles, list) else list(BUS_ROLES),
            odd_even_stereo_pairing=bool(pool_raw.get("odd_even_stereo_pairing")),
        )

    surface: Surface | None = None
    surface_raw = raw.get("surface")
    if isinstance(surface_raw, dict):
        banks = [
            Bank(id=str(b.get("id") or i + 1), label=str(b.get("label") or ""), faders=faders)
            for i, b in enumerate(surface_raw.get("banks") or [])
            if isinstance(b, dict) and (faders := _int(b.get("faders"))) is not None
        ]
        surface = Surface(banks=banks, layers=max(_int(surface_raw.get("layers")) or 1, 1))

    expansion = [
        ExpansionPort(
            protocol=str(p.get("protocol")).lower(),
            slots=_int(p.get("slots")),
            max_channels=_int(p.get("max_channels")),
            max_channels_in=_int(p.get("max_channels_in")),
            max_channels_out=_int(p.get("max_channels_out")),
        )
        for p in raw.get("expansion_ports") or []
        if isinstance(p, dict) and p.get("protocol")
    ]

    architecture = str(raw.get("architecture") or "").lower()
    if architecture not in ARCHITECTURES:
        architecture = "digital_bus_pool" if pool else "simple"
    return MixerProfile(
        architecture=architecture,  # type: ignore[arg-type]
        dsp_inputs=dsp,
        bus_pool=pool,
        dcas=_int(raw.get("dcas")) or 0,
        surface=surface,
        expansion_ports=expansion,
        source="stockwire",
    )


# --- presets ----------------------------------------------------------------------------------

_GLD_POOL = {"stereo_slot_cost": 2, "lcr_slot_cost": 3, "odd_even_stereo_pairing": False}

PRESETS: dict[str, dict] = {
    "gld-80": {
        "name": "Allen & Heath GLD-80",
        "architecture": "digital_bus_pool",
        "dsp_inputs": {"mono": 48, "stereo": 2, "fx_returns": 8},
        "bus_pool": {"total_slots": 30, "max_mixes": 20, **_GLD_POOL},
        "dcas": 16,
        "surface": {
            "banks": [
                {"id": "A", "label": "Left Bank", "faders": 12},
                {"id": "B", "label": "Right Bank", "faders": 8},
            ],
            "layers": 4,
        },
        "expansion_ports": [{"protocol": "dsnake", "max_channels_in": 48, "max_channels_out": 24}],
    },
    "gld-112": {
        "name": "Allen & Heath GLD-112",
        "architecture": "digital_bus_pool",
        "dsp_inputs": {"mono": 48, "stereo": 2, "fx_returns": 8},
        "bus_pool": {"total_slots": 30, "max_mixes": 20, **_GLD_POOL},
        "dcas": 16,
        "surface": {
            "banks": [
                {"id": "A", "label": "Left Bank", "faders": 20},
                {"id": "B", "label": "Right Bank", "faders": 8},
            ],
            "layers": 4,
        },
        "expansion_ports": [{"protocol": "dsnake", "max_channels_in": 48, "max_channels_out": 24}],
    },
    "sq-5": {
        "name": "Allen & Heath SQ-5",
        "architecture": "digital_bus_pool",
        "dsp_inputs": {"mono": 48, "stereo": 3, "fx_returns": 8},
        "bus_pool": {
            "total_slots": 12,
            "max_mixes": 12,
            "stereo_slot_cost": 2,
            "lcr_slot_cost": 3,
            "odd_even_stereo_pairing": True,
        },
        "dcas": 16,
        "surface": {"banks": [{"id": "A", "label": "Surface", "faders": 16}], "layers": 3},
        "expansion_ports": [{"protocol": "dsnake", "max_channels_in": 48, "max_channels_out": 24}],
    },
    "cq-18t": {
        "name": "Allen & Heath CQ-18T (compact digital, fixed routing)",
        "architecture": "simple",
        "dsp_inputs": {"mono": 16, "stereo": 1, "fx_returns": 0},
        "bus_pool": None,
        "dcas": 0,
        "surface": None,
        "expansion_ports": [],
    },
    "analog": {
        "name": "Generic analog console",
        "architecture": "simple",
        "dsp_inputs": {"mono": 0, "stereo": 0, "fx_returns": 0},
        "bus_pool": None,
        "dcas": 0,
        "surface": None,
        "expansion_ports": [],
    },
}


def preset_profile(key: str) -> MixerProfile | None:
    raw = PRESETS.get(key)
    if raw is None:
        return None
    return MixerProfile.model_validate({**raw, "source": "preset", "preset": key})


def list_presets() -> list[dict]:
    return [
        {"key": key, "name": raw["name"], "architecture": raw["architecture"]}
        for key, raw in PRESETS.items()
    ]


def profile_from_stored(stored: Any) -> MixerProfile | None:
    """The stored ``mixer_profile`` attribute as a model; ``None`` when absent or unreadable.

    A stored profile that no longer validates (e.g. a model change) degrades to "simple console"
    rather than breaking every read of the list.
    """
    if not isinstance(stored, dict) or not stored:
        return None
    try:
        return MixerProfile.model_validate(stored)
    except ValueError:
        return None


def is_simple(profile: MixerProfile | None) -> bool:
    """Simple consoles have no bus pool to budget and no surface to map."""
    return profile is None or profile.bus_pool is None


# --- bus pool ---------------------------------------------------------------------------------


def slot_width(mode: str | None, pool: BusPool) -> int:
    """Slots one bus consumes: mono 1, stereo ``stereo_slot_cost``, LCR ``lcr_slot_cost``."""
    if mode == "stereo":
        return pool.stereo_slot_cost
    if mode == "lcr":
        return pool.lcr_slot_cost
    return 1


def assign_slots(buses: Iterable[dict], pool: BusPool) -> list[dict]:
    """Place buses into the pool in order and return each with its 1-based ``slot_start/slot_end``.

    Stereo and LCR buses take *contiguous* slots. With ``odd_even_stereo_pairing`` a multi-slot bus
    must start on an odd slot, so an even start is bumped by one and that slot is counted as
    ``wasted`` (it cannot hold anything else). Order is the buses' given order (their position).
    """
    placed: list[dict] = []
    cursor = 1
    for bus in buses:
        width = slot_width(bus.get("mode"), pool)
        wasted = 0
        if pool.odd_even_stereo_pairing and width > 1 and cursor % 2 == 0:
            cursor += 1
            wasted = 1
        placed.append(
            {
                **bus,
                "width": width,
                "slot_start": cursor,
                "slot_end": cursor + width - 1,
                "wasted": wasted,
            }
        )
        cursor += width
    return placed


def fx_sends_in_pool(profile: MixerProfile | None) -> bool:
    """Whether built-in FX send masters draw from the bus pool: when the console lists ``fx_send``
    among its pool roles. On an Allen & Heath GLD the FX sends are one of the 30 assignable bus
    types (but are not counted among the 20 processed mixes); a console that does not list the role
    keeps its FX sends outside the pool. Remove ``fx_send`` from the allowed roles to opt out.
    """
    return bool(profile and profile.bus_pool and "fx_send" in profile.bus_pool.allowed_roles)


def bus_budget(
    profile: MixerProfile | None, buses: Iterable[dict], fx: list[dict] | None = None
) -> dict:
    """The live bus-pool budget: ``sum(count * slot_width) <= total_slots`` plus role/mix limits.

    ``buses`` are ``{id, name, mode, role}`` dicts in position order. ``fx`` are the built-in FX
    engines; when ``fx_sends_in_pool`` each engine's send takes a slot (``send_mode`` mono by
    default) *after* the real buses, but is not a mix, so it does not count towards ``max_mixes``.
    Returns a JSON-ready dict; ``enabled`` is False for simple consoles (nothing is enforced).
    ``violations`` lists every broken rule in plain text so the UI can warn without re-deriving
    them.
    """
    buses = list(buses)
    if profile is None or profile.bus_pool is None:
        return {
            "enabled": False,
            "ok": True,
            "total_slots": None,
            "used_slots": 0,
            "free_slots": None,
            "over_by": 0,
            "bus_count": len(buses),
            "max_mixes": None,
            "entries": [],
            "violations": [],
        }
    pool = profile.bus_pool
    entries = list(buses)
    if fx_sends_in_pool(profile):
        entries += [
            {
                "id": fx_send_strip_id(engine["id"]),
                "name": f"{engine.get('name') or 'FX'} send",
                "mode": engine.get("send_mode") or "mono",
                "role": "fx_send",
                "virtual": True,
            }
            for engine in fx or []
            if engine.get("configured", True)
        ]
    placed = assign_slots(entries, pool)
    used = sum(b["width"] + b["wasted"] for b in placed)
    mixes = [b for b in placed if not b.get("virtual")]
    violations: list[str] = []
    if used > pool.total_slots:
        violations.append(f"Bus pool exceeded: {used} slots needed, {pool.total_slots} available")
    if pool.max_mixes is not None and len(mixes) > pool.max_mixes:
        violations.append(f"Too many mixes: {len(mixes)} buses, console allows {pool.max_mixes}")
    for bus in mixes:
        role = bus.get("role") or "aux"
        if role not in pool.allowed_roles:
            violations.append(
                f"Bus '{bus.get('name')}' has role '{role}', not allowed on this console"
            )
    return {
        "enabled": True,
        "ok": not violations,
        "total_slots": pool.total_slots,
        "used_slots": used,
        "free_slots": max(pool.total_slots - used, 0),
        "over_by": max(used - pool.total_slots, 0),
        "bus_count": len(mixes),
        "fx_send_slots": sum(b["width"] for b in placed if b.get("virtual")),
        "max_mixes": pool.max_mixes,
        "entries": placed,
        "violations": violations,
    }


# --- mono channel linking ---------------------------------------------------------------------


class LinkError(ValueError):
    """A stereo link request that breaks a pairing rule (mapped to HTTP 409/422 by the router)."""


def check_link(
    primary: int,
    secondary: int,
    profile: MixerProfile | None,
    *,
    mixer_inputs: int | None = None,
) -> None:
    """Raise ``LinkError`` unless ``primary``/``secondary`` may be ganged into one stereo strip.

    Rules: the strips must be adjacent (``secondary == primary + 1``); with ``odd_even`` pairing the
    primary must be odd (1-2, 3-4); both must be real mono DSP strips, so the pair must fit inside
    ``dsp_inputs.mono`` (or ``mixer_inputs`` for a simple console that sets one).
    """
    if secondary != primary + 1:
        raise LinkError("Only adjacent channels (N and N+1) can be linked")
    pairing = profile.input_pairing if profile else "odd_even"
    if pairing == "odd_even" and primary % 2 == 0:
        raise LinkError(
            "Channels pair odd/even on this console: link "
            f"Ch {primary - 1}-{primary}, or Ch {primary + 1}-{primary + 2}"
        )
    limit = None
    if profile and profile.dsp_inputs.mono:
        limit = profile.dsp_inputs.mono
    elif mixer_inputs:
        limit = mixer_inputs
    if limit is not None and secondary > limit:
        raise LinkError(f"Ch {secondary} is beyond the console's {limit} mono inputs")


# What a stereo link binds: the strip's DSP identity (name, colour, group) and +48V, which an
# Allen & Heath desk links across a stereo pair. Anything about the physical source or its patch
# (input type, mic, stand, which socket / stagebox it comes from) stays per channel: the two legs
# may be patched from different stageboxes or sockets, so linking never touches patching. Ganging
# (up to 8 channels with selectable parameter groups) is a different feature, not modelled here.
SHARED_FIELDS = ("source_label", "color_code", "instrument_group", "phantom_power")


def leg_label(primary_label: str | None) -> str | None:
    """The secondary leg's name from the primary's: ``Keys L`` -> ``Keys R`` (else unchanged)."""
    import re

    match = re.fullmatch(r"(.*\S)\s+L", primary_label or "")
    return f"{match.group(1)} R" if match else primary_label


def mirrored_fields(primary_attrs: dict) -> dict:
    """The DSP parameters the secondary strip inherits from its primary.

    A key the primary no longer has (cleared) must clear on the secondary too, so every shared
    field is returned and ``None`` means "remove it". The name follows the primary but keeps the
    side: a primary named "Keys L" gives "Keys R".
    """
    shared = {key: primary_attrs.get(key) for key in SHARED_FIELDS}
    shared["source_label"] = leg_label(shared.get("source_label"))
    return shared


# --- fader map --------------------------------------------------------------------------------


def fader_slot_key(layer: int, bank: str, fader: int) -> str:
    return f"{layer}:{bank}:{fader}"


FX_TYPES = ("reverb", "delay", "chorus", "other")


def _default_fx_name(index: int) -> str:
    return f"FX {index}"


def fx_is_configured(engine: dict) -> bool:
    """An engine the engineer actually set up: it has sends, a custom name, or a chosen type."""
    import re

    name = str(engine.get("name") or "")
    return bool(
        engine.get("sends")
        or (name and not re.fullmatch(r"FX \d+", name))
        or str(engine.get("type") or "other") != "other"
    )


def effective_fx(profile: MixerProfile | None, stored: list[dict] | None) -> list[dict]:
    """The console's FX engines: the configured ones plus the rest of its built-in engines.

    A console with ``dsp_inputs.fx_returns`` = N physically has N FX engines (a GLD-80 has 8), each
    with a send master and a return strip on the surface whether or not anyone has set it up. So the
    stored (configured) engines are topped up with default placeholders ``fx1``..``fxN`` named
    "FX n", flagged ``configured: False``; they appear in the fader map and can be DCA members, but
    do not draw from the bus pool until configured. A console that states no FX returns just has
    what was stored.
    """
    engines = [{**e, "configured": True} for e in stored or []]
    total = profile.dsp_inputs.fx_returns if profile else 0
    used = {e["id"] for e in engines}
    index = 0
    while len(engines) < total:
        index += 1
        engine_id = f"fx{index}"
        if engine_id in used:
            continue
        used.add(engine_id)
        engines.append(
            {
                "id": engine_id,
                "name": _default_fx_name(len(engines) + 1),
                "type": "other",
                "stereo_return": True,
                "send_mode": "mono",
                "sends": [],
                "configured": False,
            }
        )
    return engines


def fx_strip_id(fx_id: str) -> str:
    """The FX *return* strip (an input-side strip, ``fx-<id>``)."""
    return f"fx-{fx_id}"


def fx_send_strip_id(fx_id: str) -> str:
    """The FX *send* master (an output-side strip, ``fxs-<id>``): the level feeding the engine."""
    return f"fxs-{fx_id}"


def fader_strips(
    profile: MixerProfile | None,
    channels: list[dict],
    buses: list[dict],
    fx: list[dict] | None = None,
    dcas: dict | None = None,
) -> list[dict]:
    """Every strip that needs a fader: inputs, FX returns, mixes, FX sends, then DCAs.

    ``id`` is what a custom layout and a DCA's members refer to: the channel id (a linked pair is
    *one* strip, owned by its primary), ``fx-<id>`` for an FX return, the bus id, ``fxs-<id>`` for
    an FX send master, or ``dca-N``. Each built-in FX engine therefore has two strips: its send
    (output) and its return (input). Engine sends are dedicated and do not draw from the bus pool.
    A DCA strip carries its configured name and member count.
    """
    strips: list[dict] = []
    for ch in sorted(channels, key=lambda c: c["channel_number"]):
        if ch.get("stereo_link_role") == "secondary":
            continue
        number = ch["channel_number"]
        linked = bool(ch.get("is_stereo_linked"))
        strips.append(
            {
                "id": str(ch.get("id") or f"ch-{number}"),
                "kind": "input",
                "label": ch.get("source_label") or f"Ch {number}",
                "number": f"{number}-{number + 1}" if linked else str(number),
                "stereo": linked,
            }
        )
    for engine in fx or []:
        strips.append(
            {
                "id": fx_strip_id(engine["id"]),
                "kind": "fx",
                "label": engine.get("name") or "FX",
                "number": engine.get("type") or "fx",
                "stereo": bool(engine.get("stereo_return", True)),
                # built-in engines nobody set up stay off the faders until added (tray / "add")
                "hidden": not engine.get("configured", True),
            }
        )
    for index, bus in enumerate(buses):
        strips.append(
            {
                "id": str(bus.get("id") or f"bus-{index}"),
                "kind": "mix",
                "label": bus.get("name") or "Mix",
                "number": bus.get("role") or "aux",
                "stereo": bus.get("mode") in ("stereo", "lcr"),
            }
        )
    for engine in fx or []:
        strips.append(
            {
                "id": fx_send_strip_id(engine["id"]),
                "kind": "fxsend",
                "label": f"{engine.get('name') or 'FX'} send",
                "number": "fx send",
                "stereo": False,
                "hidden": not engine.get("configured", True),
            }
        )
    for dca in range(1, (profile.dcas if profile else 0) + 1):
        config = (dcas or {}).get(str(dca)) or {}
        members = config.get("members") or []
        strips.append(
            {
                "id": f"dca-{dca}",
                "kind": "dca",
                "label": config.get("name") or f"DCA {dca}",
                "number": str(dca),
                "stereo": False,
                "members": len(members),
            }
        )
    return strips


def fader_slots(profile: MixerProfile) -> list[tuple[str, int, str, int]]:
    """All physical slots in default fill order: ``(key, layer, bank_id, fader)``."""
    slots = []
    for layer in range(1, profile.surface.layers + 1):
        for bank in profile.surface.banks:
            for fader in range(1, bank.faders + 1):
                slots.append((fader_slot_key(layer, bank.id, fader), layer, bank.id, fader))
    return slots


def validate_fader_layout(profile: MixerProfile | None, layout: dict, strip_ids: set[str]) -> dict:
    """The layout normalised, or ``ValueError`` naming the first broken rule.

    ``layout`` maps a slot key (``layer:bank:fader``) to a strip id, or to ``"empty"`` to keep the
    slot deliberately blank. Rules: the console has a surface; every slot exists; every id is a real
    strip (secondary legs of a pair are not strips). The same strip may sit on several faders (the
    same input on two layers, a mix master on both banks).
    """
    if profile is None or profile.surface is None or not profile.surface.banks:
        raise ValueError("This console has no control surface to lay out")
    valid_slots = {key for key, *_ in fader_slots(profile)}
    clean: dict[str, str] = {}
    for key, value in (layout or {}).items():
        if value in (None, ""):
            continue  # an unset slot is simply not pinned
        if key not in valid_slots:
            raise ValueError(f"No such fader slot: {key}")
        value = str(value)
        if value != "empty":
            if value not in strip_ids:
                raise ValueError(f"Unknown strip for slot {key}")
        clean[key] = value
    return clean


def fader_map(
    profile: MixerProfile | None,
    channels: list[dict],
    buses: list[dict],
    layout: dict | None = None,
    fx: list[dict] | None = None,
    dcas: dict | None = None,
) -> dict:
    """A cheat-sheet of where everything sits on the physical surface (spec §7).

    Without a stored ``layout`` the surface shows the *starting point*: strips fill layer 1 across
    every bank left to right, then layer 2, and so on (inputs, FX returns, mixes, FX sends, DCAs),
    and it follows the console as channels are added. Once a layout is stored it is exactly what the
    engineer placed: nothing is filled in behind their back, a strip they have not put anywhere is
    simply *unplaced* (offered in the tray, counted in ``unplaced``), and the same strip may sit on
    several faders. ``fader_autofill`` (the "Auto fill" / reset buttons) is the only thing that
    lays out the default again. Pins whose strip no longer exists are ignored.
    """
    if profile is None or profile.surface is None or not profile.surface.banks:
        return {"enabled": False, "layers": [], "overflow": 0, "capacity": 0, "custom": False}
    strips = fader_strips(profile, channels, buses, fx, dcas)
    by_id = {s["id"]: s for s in strips}
    pinned: dict[str, dict | None] = {}
    placed: set[str] = set()
    for key, value in (layout or {}).items():
        if value == "empty":
            pinned[key] = None
        elif value in by_id:
            pinned[key] = by_id[value]  # a strip may be pinned on several faders
            placed.add(value)
    # Hidden strips (built-in FX nobody set up) are not auto-placed; they stay in ``strips`` so the
    # tray can offer them and a pin or ``fader_add`` puts them on the surface.
    manual = bool(layout)
    queue = [] if manual else [s for s in strips if s["id"] not in placed and not s.get("hidden")]
    slots = fader_slots(profile)
    cells: dict[str, dict] = {}
    for key, _layer, _bank, fader in slots:
        if key in pinned:
            strip = pinned[key]
            is_pinned = True
        else:
            strip = queue.pop(0) if queue else None
            is_pinned = False
        cells[key] = {
            "fader": fader,
            "slot": key,
            "pinned": is_pinned,
            **(strip or {"id": None, "kind": "empty", "label": "", "number": "", "stereo": False}),
        }
    counts: dict[str, int] = {}
    for cell in cells.values():
        if cell["id"]:
            counts[cell["id"]] = counts.get(cell["id"], 0) + 1
    for cell in cells.values():
        cell["duplicate"] = bool(cell["id"]) and counts.get(cell["id"], 0) > 1
    layers = []
    for layer_no in range(1, profile.surface.layers + 1):
        banks_out = [
            {
                "id": bank.id,
                "label": bank.label,
                "strips": [
                    cells[fader_slot_key(layer_no, bank.id, f)] for f in range(1, bank.faders + 1)
                ],
            }
            for bank in profile.surface.banks
        ]
        layers.append({"layer": layer_no, "banks": banks_out})
    return {
        "enabled": True,
        "layers": layers,
        "overflow": len(queue),
        # strips (not hidden) the engineer has not put on any fader; only meaningful once manual
        "unplaced": sum(1 for s in strips if not counts.get(s["id"]) and not s.get("hidden"))
        if manual
        else 0,
        "capacity": sum(b.faders for b in profile.surface.banks),
        "custom": manual,
        "strips": [{**strip, "placements": counts.get(strip["id"], 0)} for strip in strips],
    }


# --- soft patch -------------------------------------------------------------------------------


def audio_sockets(devices: Iterable[Any]) -> list[dict]:
    """Every physical audio socket on every device of the graph (the soft-patch endpoints).

    ``AudioPort`` is deliberately *not* tied to the console: any graph device with an audio port
    (stagebox, wireless rack, Dante card, the console itself) contributes sockets, so adding or
    hot-swapping a stagebox makes its sockets appear here with no extra step. A port group with
    ``channels`` = 24 yields sockets 1..24. Channel/output/list nodes are logical, not hardware.
    """
    sockets: list[dict] = []
    for device in devices:
        if device.kind in ("channel", "output", "channel_list"):
            continue
        for port in device.ports or []:
            if port.get("signal") not in (None, "audio"):
                continue
            direction = port.get("direction") or "in"
            count = port.get("channels") or 1
            for index in range(1, int(count) + 1):
                sockets.append(
                    {
                        "device_id": str(device.id),
                        "device_name": device.name,
                        "port_id": port.get("id"),
                        "socket": index,
                        "direction": direction,
                        "connector": port.get("connector"),
                        "key": f"{device.id}:{port.get('id')}:{index}",
                    }
                )
    return sockets


def socket_key(ref: dict | None) -> str | None:
    """Canonical key of a stored ``{device_id, port_id, socket}`` reference."""
    if not ref:
        return None
    return f"{ref.get('device_id')}:{ref.get('port_id')}:{ref.get('socket') or 1}"


# --- proposing a mixer for a list --------------------------------------------------------------


def mixer_need(channels: list[dict], buses: list[dict]) -> dict:
    """What a channel list asks of a console: DSP strips, mixes, and bus-pool slots.

    ``channels`` need ``channel_number``; ``buses`` are ``{name, mode, role}``. A stereo-linked pair
    still occupies two mono strips (that is what linking means), so strips are simply the channel
    count, but never fewer than the highest channel number (a list that reaches Ch 32 needs 32
    strips even with gaps). Slots are priced at the default costs (stereo 2, LCR 3) because the
    candidate's own costs are only known per product; ``fit_mixer`` re-prices with the real ones.
    """
    numbers = [int(c.get("channel_number") or 0) for c in channels]
    strips = max(len(channels), max(numbers, default=0))
    default_pool = BusPool(total_slots=0)
    slots = sum(slot_width(b.get("mode"), default_pool) for b in buses)
    return {
        "strips": strips,
        "mixes": len(buses),
        "bus_slots": slots,
        "roles": sorted({b.get("role") or "aux" for b in buses}),
        "stereo_pairs": sum(1 for c in channels if c.get("stereo_link_role") == "primary"),
    }


def _flat(value: Any) -> int | None:
    number = _int(value)
    return number or None


def fit_mixer(need: dict, buses: list[dict], product: dict) -> dict:
    """Does ``product`` cover ``need``? Returns ``fits``, plain-text ``reasons`` and headroom.

    A product with ``specs.mixer`` is judged on its real DSP strips and bus pool (the candidate's
    own slot costs, odd/even pairing, mix limit and allowed roles, via ``bus_budget``). A product
    without it is a *simple* console (analog / compact digital with fixed routing): it must offer
    enough flat inputs, and enough flat outputs for one direct send per mix. Unknown capacities are
    not counted against a product, they are reported as ``unknown`` so the engineer can check.
    """
    specs = (product or {}).get("specs") or {}
    profile = parse_mixer_specs(product)
    reasons: list[str] = []
    unknown: list[str] = []
    headroom: dict[str, int | None] = {"strips": None, "bus_slots": None}

    if profile is not None and profile.dsp_inputs.mono:
        capacity = profile.dsp_inputs.mono
    else:
        capacity = _flat(specs.get("inputs"))
    if capacity is None:
        unknown.append("input count")
    else:
        headroom["strips"] = capacity - need["strips"]
        if capacity < need["strips"]:
            reasons.append(f"{capacity} inputs, {need['strips']} needed")

    if profile is not None and profile.bus_pool is not None:
        budget = bus_budget(profile, buses)
        headroom["bus_slots"] = budget["total_slots"] - budget["used_slots"]
        reasons.extend(budget["violations"])
    elif need["mixes"]:
        outputs = _flat(specs.get("outputs"))
        if outputs is None:
            unknown.append("output count")
        else:
            headroom["bus_slots"] = outputs - need["mixes"]
            if outputs < need["mixes"]:
                reasons.append(f"{outputs} outputs, {need['mixes']} mixes needed")

    return {
        "fits": not reasons,
        "simple": is_simple(profile),
        "architecture": profile.architecture if profile else "simple",
        "reasons": reasons,
        "unknown": unknown,
        "headroom": headroom,
    }


def rank_proposals(proposals: list[dict]) -> list[dict]:
    """Fitting consoles first and tightest first (least spare capacity); misfits follow."""

    def waste(p: dict) -> int:
        spare = [v for v in p["headroom"].values() if v is not None]
        return sum(abs(v) for v in spare) if spare else 10**6

    return sorted(proposals, key=lambda p: (not p["fits"], bool(p["unknown"]), waste(p)))


# --- soft patch <-> patch chain ----------------------------------------------------------------
#
# Two views of the same fact. The *patch chain* (a channel's ordered ``points``) is the original
# workflow: source -> ... -> the device that finally feeds the strip, each hop with a free-text
# ``patch_label``. The *soft patch* (``dsp_source``) is the structured form of the last hop: which
# socket of which device. They are kept in step:
#
# - soft patch -> chain (``console_service.sync_to_chain``): setting a socket writes/updates the
#   chain's last point for that device (``patch_label`` = "In 5", connector = the port's);
# - chain -> soft patch (``reconcile_soft_patch``, run on every graph sync): the chain's last point
#   is parsed; when its device has audio input sockets and the label names a free one, that socket
#   becomes ``dsp_source``. The chain wins when the two disagree, because it is what the rest of the
#   app (cable routing, patch sheets, edges) already reads.


def parse_socket(label: str | None) -> int | None:
    """The socket number in a patch label: ``In 5`` / ``5`` / ``XLR5`` / ``Input 05`` -> 5."""
    import re

    match = re.search(r"(\d+)", label or "")
    number = int(match.group(1)) if match else 0
    return number or None


def input_sockets_of(device: Any) -> list[dict]:
    return [s for s in audio_sockets([device]) if s["direction"] in ("in", "both")]


def derive_from_chain(
    attrs: dict,
    points: list[dict],
    devices: dict[str, Any],
    input_sockets: dict[str, list[dict]] | None = None,
) -> tuple[dict | None, str]:
    """The ``dsp_source`` a channel's chain implies, and how it was decided.

    Returns ``(ref, status)``; status is ``derived`` (the chain's strip-side hop names a socket),
    ``kept`` (it names only the device the soft patch already points at) or ``none``.

    An input socket may feed several strips at once (one source split to FOH and monitor channels
    for separate processing), so nothing here refuses a socket another strip already uses; the
    soft-patch endpoints warn about it instead.
    """
    current = attrs.get("dsp_source")
    ordered = sorted(points, key=lambda p: p.get("position") or 0, reverse=True)
    # The soft-patched hop is the one the soft patch already points at, wherever it sits in the
    # chain (extra hops such as an analog snake may be added around it); with none yet, the last.
    tail = next(
        (
            p
            for p in ordered
            if current
            and str(p.get("device_id")) == str(current.get("device_id"))
            and str(p.get("device_id")) in devices
        ),
        None,
    ) or next((p for p in ordered if str(p.get("device_id")) in devices), None)
    device = devices.get(str(tail.get("device_id"))) if tail else None
    # ``input_sockets`` lets a sync that derives many strips expand each device's sockets once
    if device is None:
        sockets: list[dict] = []
    elif input_sockets is not None:
        sockets = input_sockets.setdefault(str(device.id), input_sockets_of(device))
    else:
        sockets = input_sockets_of(device)
    if not sockets:
        return None, "none"
    valid = {s["key"] for s in sockets}
    number = parse_socket(tail.get("patch_label"))
    if number:
        connector = str(tail.get("connector") or "").lower()
        ports: dict[str, dict] = {}
        for s in sockets:
            ports.setdefault(s["port_id"], s)
        for first in sorted(
            ports.values(), key=lambda s: str(s.get("connector") or "").lower() != connector
        ):
            ref = {"device_id": first["device_id"], "port_id": first["port_id"], "socket": number}
            if socket_key(ref) in valid:
                return ref, "derived"
    if current and str(current.get("device_id")) == str(tail.get("device_id")):
        if socket_key(current) in valid:
            return current, "kept"
    return None, "none"


# --- DCAs and built-in FX ----------------------------------------------------------------------


def validate_dca_config(profile: MixerProfile | None, config: dict, member_ids: set[str]) -> dict:
    """DCA names and members, normalised; ``ValueError`` names the first broken rule.

    ``config`` maps a DCA number (``"1"``..``"N"``) to ``{"name", "members"}``. A strip may sit in
    several DCAs (an input can be in both "Drums" and "Band"), but not twice in the same one.
    Members are input strips (the primary of a linked pair), FX returns (``fx-<id>``) or mixes.
    """
    if profile is None or not profile.dcas:
        raise ValueError("This console has no DCAs")
    clean: dict[str, dict] = {}
    for key, value in (config or {}).items():
        try:
            number = int(key)
        except (TypeError, ValueError):
            raise ValueError(f"Not a DCA number: {key}") from None
        if not 1 <= number <= profile.dcas:
            raise ValueError(f"DCA {number} does not exist (the console has {profile.dcas})")
        value = value or {}
        members = [str(m) for m in value.get("members") or []]
        if len(set(members)) != len(members):
            raise ValueError(f"DCA {number} lists a strip twice")
        unknown = [m for m in members if m not in member_ids]
        if unknown:
            raise ValueError(f"DCA {number} has an unknown member: {unknown[0]}")
        name = str(value.get("name") or "").strip()
        if name or members:
            clean[str(number)] = {"name": name, "members": members}
    return clean


def validate_fx_config(
    profile: MixerProfile | None, fx: list[dict], channel_ids: set[str]
) -> list[dict]:
    """Built-in FX engines normalised: unique ids, a known type, sends only from real inputs.

    The number of engines is capped by the console's ``dsp_inputs.fx_returns`` when it states one
    (each engine has one return strip); a console that does not state it is not capped.
    """
    cap = profile.dsp_inputs.fx_returns if profile else 0
    if cap and len(fx) > cap:
        raise ValueError(f"The console has {cap} FX returns, {len(fx)} FX engines configured")
    seen: set[str] = set()
    clean: list[dict] = []
    for engine in fx:
        fx_id = str(engine.get("id") or "").strip()
        if not fx_id:
            raise ValueError("Every FX engine needs an id")
        if fx_id in seen:
            raise ValueError(f"FX engine {fx_id} is listed twice")
        seen.add(fx_id)
        kind = str(engine.get("type") or "other").lower()
        if kind not in FX_TYPES:
            raise ValueError(f"FX type must be one of {', '.join(FX_TYPES)}")
        sends = [str(c) for c in engine.get("sends") or []]
        if len(set(sends)) != len(sends):
            raise ValueError(f"FX {fx_id} lists a channel twice")
        unknown = [c for c in sends if c not in channel_ids]
        if unknown:
            raise ValueError(f"FX {fx_id} sends from an unknown channel: {unknown[0]}")
        send_mode = str(engine.get("send_mode") or "mono").lower()
        if send_mode not in ("mono", "stereo"):
            raise ValueError("FX send_mode must be mono or stereo")
        clean.append(
            {
                "id": fx_id,
                "name": str(engine.get("name") or "").strip() or f"FX {len(clean) + 1}",
                "type": kind,
                "stereo_return": bool(engine.get("stereo_return", True)),
                "send_mode": send_mode,
                "sends": sends,
            }
        )
    # placeholders (unconfigured built-in engines) are not stored: they are re-created from the
    # console's FX return count, so storage only holds what the engineer set up
    return [e for e in clean if fx_is_configured(e)]


# --- expansion slots ---------------------------------------------------------------------------


def validate_expansion(profile: MixerProfile | None, installed: list[dict]) -> list[dict]:
    """Installed expansion cards / ports checked against the console's ``expansion_ports``.

    Each entry is ``{protocol, channels_in, channels_out}``. The protocol must be one the console
    offers (edit the profile's expansion ports first to add a custom one); channel counts may not
    exceed that port's ``max_channels_in/out`` (or ``max_channels``); a protocol cannot be installed
    more often than its ``slots`` (a fixed port such as dSNAKE counts as one).
    """
    offered = {p.protocol.lower(): p for p in (profile.expansion_ports if profile else [])}
    if not offered and installed:
        raise ValueError("This console lists no expansion ports; add them to the profile first")
    counts: dict[str, int] = {}
    clean: list[dict] = []
    for entry in installed:
        protocol = str(entry.get("protocol") or "").strip().lower()
        port = offered.get(protocol)
        if port is None:
            raise ValueError(f"The console has no {protocol or '?'} expansion port")
        counts[protocol] = counts.get(protocol, 0) + 1
        if counts[protocol] > (port.slots or 1):
            raise ValueError(f"Only {port.slots or 1} {protocol} slot(s) available")
        sides = {}
        for side, specific in (("in", port.max_channels_in), ("out", port.max_channels_out)):
            wanted = _int(entry.get(f"channels_{side}")) or 0
            limit = specific if specific is not None else port.max_channels
            if limit is not None and wanted > limit:
                raise ValueError(f"{protocol} supports at most {limit} channels {side}")
            sides[side] = wanted
        if not (sides["in"] or sides["out"]):
            raise ValueError(f"{protocol} needs at least one channel in or out")
        clean.append(
            {
                "id": f"{protocol}-{counts[protocol]}",
                "protocol": protocol,
                "channels_in": sides["in"],
                "channels_out": sides["out"],
            }
        )
    return clean


BUS_WIDTH = {"mono": 1, "stereo": 2, "lcr": 3}


def bus_width(mode: str | None) -> int:
    """Sockets one bus endpoint needs: mono 1, stereo 2 (L, R), LCR 3 (L, R, C)."""
    return BUS_WIDTH.get(str(mode or "mono"), 1)


def soft_patch_plan(
    sockets: list[dict],
    taken: set[str],
    channels: list[dict],
    device_id: str,
    port_id: str,
    start: int = 1,
    skip_taken: bool = True,
    direction: str = "in",
    id_key: str = "channel_id",
) -> list[dict]:
    """Assign items (channels or buses, in the given order) to consecutive sockets of one port.

    ``direction`` picks input sockets (soft patch) or output sockets (direct outs, bus outputs).
    An item with ``width`` > 1 (a stereo bus = 2, LCR = 3) takes that many *adjacent* sockets, e.g.
    ``[3, 4]``, reported in ``sockets``; ``socket`` is its first. Starts at ``start``. A socket
    already ``taken`` is skipped when ``skip_taken`` (a stereo pair needs a free adjacent run),
    else it is an error. ``ValueError`` when the port runs out, so the engineer sees what fits
    instead of a half-applied patch.
    """
    ordered = sorted(
        (
            s
            for s in sockets
            if s["device_id"] == device_id
            and s["port_id"] == port_id
            and s["direction"] in (direction, "both")
            and s["socket"] >= start
        ),
        key=lambda s: s["socket"],
    )
    if not ordered:
        raise ValueError("No such port, or no sockets at or after the start socket")
    by_number = {s["socket"]: s for s in ordered}
    plan: list[dict] = []
    cursor = ordered[0]["socket"]
    last = ordered[-1]["socket"]
    for item in channels:
        width = max(int(item.get("width") or 1), 1)
        while True:
            run = [cursor + i for i in range(width)]
            if run[-1] > last or any(n not in by_number for n in run):
                if run[-1] > last:
                    raise ValueError(
                        f"The port has no free socket left for {item.get('name') or item['id']} "
                        f"({len(plan)} of {len(channels)} fit)"
                    )
                cursor += 1
                continue
            busy = [n for n in run if by_number[n]["key"] in taken]
            if busy:
                if not skip_taken:
                    raise ValueError(f"Socket {busy[0]} is already in use")
                cursor = busy[-1] + 1
                continue
            break
        plan.append(
            {
                id_key: item["id"],
                "channel_number": item.get("channel_number"),
                "name": item.get("name"),
                "device_id": device_id,
                "port_id": port_id,
                "socket": run[0],
                "sockets": run,
            }
        )
        cursor = run[-1] + 1
    return plan


def fader_autofill(
    profile: MixerProfile | None,
    channels: list[dict],
    buses: list[dict],
    layout: dict | None,
    fx: list[dict] | None,
    dcas: dict | None,
    mode: str = "all",
) -> dict:
    """A stored layout from the default fill: the "start" and "reset" of the fader map.

    ``all`` discards the current layout and lays everything out from the top (the starting point,
    now stored, so from here on it is the engineer's). ``missing`` keeps what is placed and puts
    every unplaced strip on the next free fader, in default order (a gap filler after adding
    channels). Hidden built-in FX are not placed by either. ``ValueError`` when ``missing`` runs out
    of faders.
    """
    default = fader_map(profile, channels, buses, None, fx, dcas)
    if not default["enabled"]:
        raise ValueError("This console has no control surface to lay out")

    def cells_of(result: dict) -> list[dict]:
        return [c for layer in result["layers"] for b in layer["banks"] for c in b["strips"]]

    if mode == "all" or not layout:
        return {c["slot"]: c["id"] for c in cells_of(default) if c["id"]}
    current = fader_map(profile, channels, buses, layout, fx, dcas)
    new_layout = dict(layout)
    free = [c["slot"] for c in cells_of(current) if not c["id"] and c["slot"] not in new_layout]
    for strip in current["strips"]:
        if strip["placements"] or strip.get("hidden"):
            continue
        if not free:
            raise ValueError("No free fader left on the surface")
        new_layout[free.pop(0)] = strip["id"]
    return new_layout


def fader_add(
    profile: MixerProfile | None,
    channels: list[dict],
    buses: list[dict],
    layout: dict | None,
    fx: list[dict] | None,
    dcas: dict | None,
    strip_ids: list[str],
    duplicate: bool = False,
) -> dict:
    """The layout with ``strip_ids`` pinned onto the first free fader slots (in the order given).

    A strip already on the surface is skipped unless ``duplicate``, which puts another copy of it on
    the next free fader (the same strip on two layers).

    "Free" is judged on the map as it is now: a slot with no pin whose auto-filled strip is not
    itself pinned later. Used to bring hidden FX strips onto the surface in one step. Raises
    ``ValueError`` when a strip is unknown or the surface is full.
    """
    current = fader_map(profile, channels, buses, layout, fx, dcas)
    if not current["enabled"]:
        raise ValueError("This console has no control surface to lay out")
    known = {s["id"] for s in current["strips"]}
    pinned_now = {
        c["id"]
        for layer in current["layers"]
        for bank in layer["banks"]
        for c in bank["strips"]
        if c["id"]
    }
    new_layout = dict(layout or {})
    # pin everything that is currently auto-placed so adding does not shuffle it around
    for layer in current["layers"]:
        for bank in layer["banks"]:
            for cell in bank["strips"]:
                if cell["id"] and not cell["pinned"]:
                    new_layout[cell["slot"]] = cell["id"]
    free = [
        c["slot"]
        for layer in current["layers"]
        for bank in layer["banks"]
        for c in bank["strips"]
        if not c["id"] and c["slot"] not in new_layout
    ]
    for strip_id in strip_ids:
        if strip_id not in known:
            raise ValueError(f"Unknown strip: {strip_id}")
        if strip_id in pinned_now and not duplicate:
            continue
        if not free:
            raise ValueError("No free fader left on the surface")
        new_layout[free.pop(0)] = strip_id
    return new_layout


def output_sockets_of(device: Any) -> list[dict]:
    return [s for s in audio_sockets([device]) if s["direction"] in ("out", "both")]


def endpoint_keys(endpoint: dict) -> list[str]:
    return [k for k in (socket_key(r) for r in endpoint.get("refs") or []) if k]


def expand_refs(ref: dict, width: int) -> list[dict]:
    """A stereo/LCR endpoint given only its first socket gets the following sockets (same port)."""
    return [{**ref, "socket": int(ref.get("socket") or 1) + i} for i in range(max(width, 1))]


def first_out_ref(endpoints: list[dict] | None) -> dict | None:
    """The first socket of the first endpoint (the single ``out_socket`` older clients read)."""
    for endpoint in endpoints or []:
        if endpoint.get("refs"):
            return endpoint["refs"][0]
    return None


def derive_out_endpoints(
    attrs: dict,
    points: list[dict],
    devices: dict[str, Any],
    taken: set[str],
    mode: str | None,
) -> list[dict]:
    """The bus's output endpoints after a chain edit (see the soft patch <-> chain notes above).

    A bus can leave from several places (main to FOH and to a recording box), each endpoint being
    one socket (mono), a pair (stereo) or three (LCR). Stored endpoints survive while a device they
    use is still on the bus's chain; one whose devices were all removed from the chain is dropped
    (the chain wins). When no endpoint is stored, the first chain hop whose device has output
    sockets and whose ``patch_label`` names one (``Out 5`` or ``Out 5-6``) yields one. Sockets in
    ``taken`` (other buses' endpoints, direct outs) are never derived.
    """
    ordered = sorted(points, key=lambda p: p.get("position") or 0)
    on_chain = {str(p.get("device_id")) for p in ordered}
    kept = [
        e
        for e in attrs.get("out_endpoints") or []
        if any(str(r.get("device_id")) in on_chain for r in e.get("refs") or [])
    ]
    if kept:
        return kept
    width = bus_width(mode)
    for point in ordered:
        device = devices.get(str(point.get("device_id")))
        number = parse_socket(point.get("patch_label"))
        if device is None or not number:
            continue
        sockets = output_sockets_of(device)
        valid = {s["key"] for s in sockets}
        connector = str(point.get("connector") or "").lower()
        ports: dict[str, dict] = {}
        for s in sockets:
            ports.setdefault(s["port_id"], s)
        for first in sorted(
            ports.values(), key=lambda s: str(s.get("connector") or "").lower() != connector
        ):
            ref = {"device_id": first["device_id"], "port_id": first["port_id"], "socket": number}
            refs = expand_refs(ref, width)
            keys = [socket_key(r) for r in refs]
            if all(k in valid for k in keys) and not any(k in taken for k in keys):
                return [{"id": str(point.get("point_id")), "refs": refs}]
    return []


def pin_soft_patch_last(points: list[dict], soft_device_id: str | None) -> list[dict] | None:
    """The chain with the soft-patched hop moved to the end (renumbered), or ``None`` if it is.

    Signal runs source -> ... -> the device whose socket feeds the DSP strip. The strip-side hop is
    therefore always the *last* one; analog snakes, splitters and patch panels go between the source
    and it. A chain edit that put something after the soft-patched device is corrected here so the
    source stays at one end and the soft patch at the other.
    """
    if not soft_device_id or not points:
        return None
    ordered = sorted(points, key=lambda p: p.get("position") or 0)
    hop = next(
        (p for p in reversed(ordered) if str(p.get("device_id")) == str(soft_device_id)), None
    )
    if hop is None or ordered[-1] is hop:
        return None
    rest = [p for p in ordered if p is not hop]
    return [{**p, "position": i} for i, p in enumerate([*rest, hop])]
