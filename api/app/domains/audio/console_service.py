"""Database-aware console rules: bus-budget guard, stereo link guards, soft-patch bookkeeping.

``console.py`` holds the pure rules; this module applies them to graph nodes. The audio router calls
the ``guard_*`` helpers before a write so the invariants hold no matter which endpoint is used:

- a bus create/update that would overflow the bus pool is refused (409) unless ``force`` is set;
- the *secondary* strip of a stereo pair follows its primary's name, colour, group and +48V, so
  those fields cannot be edited on it directly (409). Everything about patching (patch points,
  soft-patch socket, direct out, input type, mic) stays per leg: each is its own preamp;
- linked strips keep their numbers (changing ``channel_number`` needs an unlink first).
"""

from __future__ import annotations

import uuid
from typing import Any

from fastapi import HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.domains.audio import console
from app.domains.graph import audio_native, devices_native
from app.domains.graph.ids import public_id
from app.domains.graph.models import GraphDevice

CONFLICT = status.HTTP_409_CONFLICT
LINK_KEYS = ("is_stereo_linked", "stereo_link_role", "stereo_partner_id")


def profile_of(list_row: Any) -> console.MixerProfile | None:
    """The stored profile of a list row (``None`` = simple console, nothing enforced)."""
    return console.profile_from_stored(getattr(list_row, "mixer_profile", None))


def buses_of(outputs: list[Any]) -> list[dict]:
    return [
        {
            "id": str(o.id),
            "name": o.name,
            "mode": getattr(o, "mode", None) or "mono",
            "role": getattr(o, "role", None) or "aux",
            "position": o.position or 0,
        }
        for o in sorted(outputs, key=lambda o: o.position or 0)
    ]


async def _list_row(db: AsyncSession, list_id: uuid.UUID, job_id: uuid.UUID):
    row = await audio_native.get_list(db, list_id, job_id)
    if row is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Channel list not found")
    return row


async def guard_bus_budget(
    db: AsyncSession,
    job_id: uuid.UUID,
    list_id: uuid.UUID,
    *,
    new: dict | None = None,
    replace: tuple[str, dict] | None = None,
    force: bool = False,
) -> dict:
    """Refuse (409) a bus write that would break the pool budget; returns the resulting budget.

    ``new`` is a bus about to be added; ``replace`` is ``(output_id, changed_fields)`` for an edit.
    Only a write that *makes things worse* is blocked: an already-over-budget list (e.g. a profile
    tightened later) can still be edited towards a valid state. ``force`` lets the engineer
    knowingly exceed the pool (the UI offers it as "add anyway").
    """
    row = await _list_row(db, list_id, job_id)
    profile = profile_of(row)
    before = buses_of(row.outputs)
    after = [dict(b) for b in before]
    if replace is not None:
        target, changes = replace
        for bus in after:
            if bus["id"] == target:
                bus.update({k: v for k, v in changes.items() if v is not None and k in bus})
        after.sort(key=lambda b: b["position"])
    if new is not None:
        after.append(
            {
                "id": "new",
                "name": new.get("name") or "Output",
                "mode": new.get("mode") or "mono",
                "role": new.get("role") or "aux",
                # the output is created at ``position`` (default: end), and slots follow order
                "position": new["position"]
                if new.get("position") is not None
                else max((b["position"] for b in after), default=0) + 1,
            }
        )
        after.sort(key=lambda b: b["position"])
    fx = console.effective_fx(profile, row.fx_config)
    budget_after = console.bus_budget(profile, after, fx)
    if budget_after["ok"] or force:
        return budget_after
    budget_before = console.bus_budget(profile, before, fx)
    if len(budget_after["violations"]) <= len(budget_before["violations"]) and (
        budget_after["over_by"] <= budget_before["over_by"]
    ):
        return budget_after
    raise HTTPException(
        CONFLICT,
        detail={"message": "; ".join(budget_after["violations"]), "budget": budget_after},
    )


async def channel_node_of(
    db: AsyncSession, job_id: uuid.UUID, channel_id: uuid.UUID
) -> GraphDevice:
    node = await audio_native.find_node(db, audio_native.CHANNEL, channel_id, job_id)
    if node is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Channel not found")
    return node


def _attrs(node: GraphDevice) -> dict:
    return node.attributes or {}


def is_secondary(node: GraphDevice) -> bool:
    return _attrs(node).get("stereo_link_role") == "secondary"


def is_linked(node: GraphDevice) -> bool:
    return bool(_attrs(node).get("is_stereo_linked"))


async def guard_channel_update(db: AsyncSession, channel_id: uuid.UUID, data: dict) -> None:
    """Pairing rules for a channel edit.

    The secondary's DSP identity (``SHARED_FIELDS``) follows its primary, so editing it directly is
    refused. Everything about the physical source and its patch stays editable on both legs, and a
    linked strip keeps its number (unlink first to renumber).
    """
    node = await audio_native.find_node(db, audio_native.CHANNEL, channel_id)
    if node is None:
        return
    if is_secondary(node) and any(key in console.SHARED_FIELDS for key in data):
        primary = _attrs(node).get("stereo_partner_id")
        raise HTTPException(
            CONFLICT,
            "This channel is the secondary of a stereo pair: its name, colour and group follow "
            f"its primary ({primary}); change them there or unlink the pair first",
        )
    if is_linked(node) and data.get("channel_number") not in (
        None,
        _attrs(node).get("channel_number"),
    ):
        raise HTTPException(CONFLICT, "Unlink the stereo pair before renumbering its channels")


def _unlinked(attrs: dict) -> dict:
    """Attributes without any stereo-link state (the new keys and the legacy pair fields)."""
    out = {k: v for k, v in attrs.items() if k not in LINK_KEYS}
    out["stereo"] = False
    out["stereo_channel"] = None
    return out


async def release_partner(db: AsyncSession, channel_id: uuid.UUID) -> GraphDevice | None:
    """Before a linked channel is deleted, clear the link on the other half; returns that node."""
    node = await audio_native.find_node(db, audio_native.CHANNEL, channel_id)
    if node is None or not is_linked(node):
        return None
    partner_id = _attrs(node).get("stereo_partner_id")
    partner = (
        await audio_native.find_node(db, audio_native.CHANNEL, uuid.UUID(str(partner_id)))
        if partner_id
        else None
    )
    if partner is None:
        return None
    partner.attributes = _unlinked(_attrs(partner))
    await db.flush()
    return partner


async def mirror_to_secondary(
    db: AsyncSession, job_id: uuid.UUID, channel_id: uuid.UUID
) -> GraphDevice | None:
    """After a primary edit, copy the shared DSP parameters onto its secondary strip."""
    node = await audio_native.find_node(db, audio_native.CHANNEL, channel_id, job_id)
    if node is None or not is_linked(node) or is_secondary(node):
        return None
    partner = await audio_native.find_node(
        db, audio_native.CHANNEL, uuid.UUID(str(_attrs(node)["stereo_partner_id"])), job_id
    )
    if partner is None:
        return None
    shared = console.mirrored_fields(_attrs(node))
    merged = {**_attrs(partner), **shared}
    partner.attributes = {k: v for k, v in merged.items() if v is not None or k not in shared}
    partner.name = audio_native._channel_name(partner.attributes)
    await db.flush()
    return partner


async def link_pair(
    db: AsyncSession,
    job_id: uuid.UUID,
    list_id: uuid.UUID,
    primary_id: uuid.UUID,
    secondary_id: uuid.UUID | None,
) -> tuple[GraphDevice, GraphDevice]:
    """Link ``Ch N`` (primary) and ``Ch N+1`` (secondary) into one stereo strip.

    When ``secondary_id`` is omitted the channel numbered N+1 in the same list is used. Both must be
    unlinked mono strips and obey the console's pairing rule. The link binds only the strip's name,
    colour, group and +48V; each leg keeps its own patch points, soft patch and direct out, because
    each is its own preamp and may be patched from a different stagebox or socket.
    """
    row = await _list_row(db, list_id, job_id)
    # channels record their list by the list *node* id, which differs from the public id (the one in
    # the URL) for a list imported from the old tables
    list_node = await audio_native.find_node(db, audio_native.LIST, list_id, job_id)
    list_key = str(list_node.id) if list_node is not None else str(list_id)
    primary = await channel_node_of(db, job_id, primary_id)
    number = _attrs(primary).get("channel_number") or primary.position
    if secondary_id is None:
        members = [c for c in row.channels if c.channel_number == number + 1]
        if not members:
            raise HTTPException(CONFLICT, f"Create Ch {number + 1} first: no channel to link with")
        secondary_id = members[0].id
    secondary = await channel_node_of(db, job_id, secondary_id)
    for node in (primary, secondary):
        if _attrs(node).get("list_id") != list_key:
            raise HTTPException(CONFLICT, "Both channels must be in this channel list")
        if is_linked(node):
            raise HTTPException(CONFLICT, f"{node.name} is already part of a stereo pair")
    try:
        console.check_link(
            number,
            _attrs(secondary).get("channel_number") or secondary.position,
            profile_of(row),
            mixer_inputs=row.mixer_inputs,
        )
    except console.LinkError as exc:
        raise HTTPException(CONFLICT, str(exc)) from exc
    s_attrs = _attrs(secondary)
    s_number = s_attrs.get("channel_number") or secondary.position
    # The link binds the DSP strip only. Patch points, soft patch and direct out of each leg are
    # untouched: the two preamps may sit on different stageboxes or sockets.
    primary.attributes = {
        **_attrs(primary),
        "is_stereo_linked": True,
        "stereo_link_role": "primary",
        "stereo_partner_id": str(public_id(secondary)),
        # legacy pair fields (the Inputs page toggle and the exports) stay in step
        "stereo": True,
        "stereo_channel": s_number,
    }
    secondary.attributes = {
        **s_attrs,
        **{k: v for k, v in console.mirrored_fields(_attrs(primary)).items() if v is not None},
        "is_stereo_linked": True,
        "stereo_link_role": "secondary",
        "stereo_partner_id": str(public_id(primary)),
        "stereo": True,
        "stereo_channel": number,
    }
    secondary.name = audio_native._channel_name(secondary.attributes)
    await db.flush()
    return primary, secondary


async def unlink_pair(
    db: AsyncSession, job_id: uuid.UUID, channel_id: uuid.UUID
) -> list[GraphDevice]:
    """Split a pair (call with either strip). Both strips become independent mono channels."""
    node = await channel_node_of(db, job_id, channel_id)
    if not is_linked(node):
        raise HTTPException(CONFLICT, "Channel is not linked")
    partner_id = _attrs(node).get("stereo_partner_id")
    nodes = [node]
    partner = (
        await audio_native.find_node(db, audio_native.CHANNEL, uuid.UUID(str(partner_id)), job_id)
        if partner_id
        else None
    )
    if partner is not None:
        nodes.append(partner)
    for each in nodes:
        each.attributes = _unlinked(_attrs(each))
    await db.flush()
    return nodes


# --- soft patch -------------------------------------------------------------------------------


async def job_hardware(db: AsyncSession, job_id: uuid.UUID) -> list[GraphDevice]:
    """The job's real gear (graph nodes behind a ``device:`` ref) that can own audio sockets.

    Logical nodes (channels, outputs, lists, plot elements) and nodes without a device ref are left
    out: a patch point can only reference a real device, so a socket on anything else could never
    be mirrored into the patch chain.
    """
    rows = await db.scalars(select(GraphDevice).where(GraphDevice.job_id == job_id))
    return [n for n in rows.all() if n.legacy_ref and n.legacy_ref.startswith("device:")]


async def job_channel_nodes(db: AsyncSession, job_id: uuid.UUID) -> list[GraphDevice]:
    rows = await db.scalars(
        select(GraphDevice).where(
            GraphDevice.job_id == job_id, GraphDevice.kind == audio_native.CHANNEL
        )
    )
    return list(rows.all())


def occupied(socket: dict, node: GraphDevice | None = None) -> list[str]:
    """Keys a strip occupies at ``socket``: always one (each leg of a pair is patched alone)."""
    key = console.socket_key(socket)
    return [key] if key else []


async def assign_socket(
    db: AsyncSession,
    job_id: uuid.UUID,
    channel_id: uuid.UUID,
    field: str,
    ref: dict | None,
) -> GraphDevice:
    """Set (or clear, with ``ref=None``) a channel's ``dsp_source`` or ``direct_out``.

    ``dsp_source`` maps a physical input socket to the DSP strip; an input socket may feed several
    strips (one source split into FOH and monitor channels). ``direct_out`` routes the strip to a
    physical output socket without taking a bus slot (it is stored on the channel, never as an
    output node, so the bus-pool budget does not see it); an output socket serves one thing only.
    Each leg of a stereo pair is patched on its own.
    """
    node = await channel_node_of(db, job_id, channel_id)
    attrs = dict(_attrs(node))
    old = attrs.get(field)
    if ref is None:
        attrs.pop(field, None)
        node.attributes = attrs
        await db.flush()
        if field == "dsp_source":
            await sync_to_chain(db, node, old, None)
        return node
    ref = {
        "device_id": str(ref["device_id"]),
        "port_id": ref["port_id"],
        "socket": ref.get("socket") or 1,
    }
    want = "in" if field == "dsp_source" else "out"
    hardware = await job_hardware(db, job_id)
    sockets = {s["key"]: s for s in console.audio_sockets(hardware)}
    for key in occupied(ref, node):
        socket = sockets.get(key)
        if socket is None:
            raise HTTPException(
                status.HTTP_422_UNPROCESSABLE_CONTENT, "No such audio socket on this job"
            )
        if socket["direction"] not in (want, "both"):
            raise HTTPException(
                status.HTTP_422_UNPROCESSABLE_CONTENT, f"Socket is not an {want}put: {key}"
            )
    wanted = set(occupied(ref, node))
    if field == "direct_out":
        # A physical *output* socket carries one thing. (An *input* socket may feed several strips:
        # one source split to FOH and monitor channels, each with its own processing. Those are
        # reported by ``shared_with`` so the caller can warn, not refused.)
        others = await db.scalars(
            select(GraphDevice).where(
                GraphDevice.job_id == job_id, GraphDevice.kind == audio_native.CHANNEL
            )
        )
        for other in others:
            if other.id == node.id or not _attrs(other).get(field):
                continue
            if set(occupied(_attrs(other)[field], other)) & wanted:
                raise HTTPException(
                    CONFLICT,
                    f"That socket is already used by {other.name} "
                    f"(Ch {_attrs(other).get('channel_number')})",
                )
    if field == "direct_out":
        # ... and not a bus output either: a direct out and a bus cannot share an output socket
        outputs = await db.scalars(
            select(GraphDevice).where(
                GraphDevice.job_id == job_id, GraphDevice.kind == audio_native.OUTPUT
            )
        )
        for bus in outputs:
            used = {
                k for e in _attrs(bus).get("out_endpoints") or [] for k in console.endpoint_keys(e)
            }
            if used & wanted:
                raise HTTPException(CONFLICT, f"That socket is already used by bus {bus.name}")
    attrs[field] = ref
    node.attributes = attrs
    await db.flush()
    if field == "dsp_source":
        # direct outs have no place in the (input-side) patch chain; only the source mirrors
        await sync_to_chain(db, node, old, ref)
    return node


async def sync_to_chain(
    db: AsyncSession, node: GraphDevice, old_ref: dict | None, new_ref: dict | None
) -> None:
    """Soft patch -> chain: make the channel's patch chain say what its ``dsp_source`` says.

    Setting a socket puts it on the chain's *last* hop: an existing point for that device is
    relabelled (``In 5``) and given the port's connector; otherwise a point is appended (flagged
    ``soft_patch`` so a later clear removes only what this created). Clearing removes the flagged
    point, and moving to another device removes the old flagged point. The graph sync that follows
    every write turns the points into edges, and ``reconcile_soft_patch`` then confirms the result
    (a no-op, because the chain now agrees).
    """
    points = [dict(p) for p in (_attrs(node).get("points") or [])]
    if old_ref and (not new_ref or str(new_ref["device_id"]) != str(old_ref["device_id"])):
        # Moving (or clearing) removes the old strip-side hop: the one this created, or (when the
        # chain was edited since and lost the flag) the last hop if it still holds the old socket.
        last = max(points, key=lambda p: p.get("position") or 0) if points else None

        def is_old_hop(p: dict) -> bool:
            if str(p.get("device_id")) != str(old_ref["device_id"]):
                return False
            return bool(p.get("soft_patch")) or (
                p is last and console.parse_socket(p.get("patch_label")) == old_ref.get("socket")
            )

        points = [p for p in points if not is_old_hop(p)]
    if new_ref:
        hardware = await job_hardware(db, node.job_id)
        device = next((d for d in hardware if str(d.id) == str(new_ref["device_id"])), None)
        port = next(
            (p for p in (device.ports if device else []) if p.get("id") == new_ref["port_id"]), {}
        )
        label = f"In {new_ref.get('socket') or 1}"
        existing = next(
            (p for p in points if str(p.get("device_id")) == str(new_ref["device_id"])), None
        )
        if existing is not None:
            existing.update(
                patch_label=label,
                connector=port.get("connector") or existing.get("connector") or "",
                revision=(existing.get("revision") or 1) + 1,
            )
            # the stagebox is the last hop into the strip: anything after it would contradict that
            existing["position"] = max((p.get("position") or 0) for p in points)
        else:
            points.append(
                {
                    "point_id": str(uuid.uuid4()),
                    "position": max((p.get("position") or 0 for p in points), default=-1) + 1,
                    "point_type": getattr(device, "kind", None) or "other",
                    "connector": port.get("connector") or "",
                    "patch_label": label,
                    "notes": "",
                    "device_id": str(new_ref["device_id"]),
                    "revision": 1,
                    "soft_patch": True,
                }
            )
    await audio_native._store_points(db, node, points)


async def assign_many(
    db: AsyncSession,
    job_id: uuid.UUID,
    assignments: list[tuple[uuid.UUID, dict | None]],
    field: str = "dsp_source",
    list_ctx: tuple[uuid.UUID, Any] | None = None,
    append: bool = False,
) -> list[GraphDevice]:
    """Apply several socket assignments as one unit: all of them, or none.

    Each goes through ``assign_socket`` (same checks: real socket, right direction, one strip per
    socket, chain sync). The first failure rolls the whole batch back and reports which channel
    broke, so a 64-channel Dante patch is never left half done.
    """
    nodes: list[GraphDevice] = []
    for channel_id, ref in assignments:
        try:
            if field == "out_socket":
                # buses: ``list_ctx`` = (list id, list row) for the chain's console hop; the ref is
                # the endpoint's first socket (a stereo / LCR bus takes the following ones)
                nodes.append(
                    await assign_output_endpoints(
                        db,
                        job_id,
                        channel_id,
                        *list_ctx,  # type: ignore[misc]
                        [[ref]] if ref else [],
                        append=append,
                    )
                )
            else:
                nodes.append(await assign_socket(db, job_id, channel_id, field, ref))
        except HTTPException as exc:
            await db.rollback()
            raise HTTPException(exc.status_code, f"{exc.detail} (channel {channel_id})") from exc
    return nodes


async def console_device(
    db: AsyncSession, job_id: uuid.UUID, list_id: uuid.UUID, row: Any
) -> GraphDevice:
    """The list's console as a real device (the mixer minted for it), created when missing.

    The device is what owns the console's own sockets and its installed expansion cards, so they
    appear in the soft patch like any stagebox. It is found by ``sound_list_id``.
    """
    rows = await db.scalars(
        select(GraphDevice).where(
            GraphDevice.job_id == job_id, GraphDevice.legacy_ref.like("device:%")
        )
    )
    for node in rows:
        if _attrs(node).get("sound_list_id") == str(list_id):
            return node
    created = await devices_native.create_device(
        db,
        job_id,
        {
            "name": row.mixer_product_name or f"{row.name} console",
            "device_type": "mixer",
            "sound_list_id": list_id,
            "stockwire_product_id": row.mixer_product_id,
            "stockwire_product_name": row.mixer_product_name,
        },
    )
    node = await db.get(GraphDevice, created.id) or await devices_native.node_of(
        db, created.id, job_id
    )
    return node


def expansion_groups(node: GraphDevice, installed: list[dict]) -> list[dict]:
    """The device's port groups with its expansion groups replaced by ``installed``'s."""
    groups = [g for g in _attrs(node).get("port_groups") or [] if not g.get("expansion")]
    for card in installed:
        for side in ("in", "out"):
            count = card.get(f"channels_{side}") or 0
            if count:
                groups.append(
                    {
                        "direction": side,
                        "connector": card["protocol"],
                        "count": count,
                        "expansion": card["id"],
                    }
                )
    return groups


def expansion_port_ids(node: GraphDevice, installed: list[dict]) -> set[str]:
    """Port ids the device would have after the change (to refuse removing ports in use)."""
    ports = devices_native.group_ports(expansion_groups(node, installed), "audio")
    others = [p["id"] for p in node.ports or [] if not devices_native._is_group_port(p)]
    return {p["id"] for p in ports} | set(others)


async def apply_expansion(db: AsyncSession, node: GraphDevice, installed: list[dict]) -> None:
    """Make the console device's ports match the installed expansion cards.

    Each card becomes real port groups on the device (``in-<protocol>`` / ``out-<protocol>`` with a
    channel count), tagged ``expansion`` so a later change replaces exactly those and leaves the
    console's own connectors alone. Because they are ordinary ports, the soft patch, the patch chain
    and the cable views treat a 64-channel Dante card like any stagebox.
    """
    attrs = dict(_attrs(node))
    groups = expansion_groups(node, installed)
    attrs["port_groups"] = groups
    node.attributes = attrs
    devices_native.rebuild_ports(node, groups)
    await db.flush()


async def output_node_of(db: AsyncSession, job_id: uuid.UUID, output_id: uuid.UUID) -> GraphDevice:
    node = await audio_native.find_node(db, audio_native.OUTPUT, output_id, job_id)
    if node is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Bus not found")
    return node


async def shared_with(
    db: AsyncSession, job_id: uuid.UUID, node: GraphDevice, ref: dict | None
) -> list[dict]:
    """Other strips that take their input from the same socket (a split source), for a warning."""
    key = console.socket_key(ref)
    if not key:
        return []
    others = []
    for other in await job_channel_nodes(db, job_id):
        if other.id != node.id and console.socket_key(_attrs(other).get("dsp_source")) == key:
            others.append(
                {
                    "channel_id": str(audio_native.public_id(other)),
                    "channel_number": _attrs(other).get("channel_number"),
                    "name": other.name,
                }
            )
    return others


def _bus_mode(node: GraphDevice) -> str:
    return _attrs(node).get("mode") or "mono"


async def assign_output_endpoints(
    db: AsyncSession,
    job_id: uuid.UUID,
    output_id: uuid.UUID,
    list_id: uuid.UUID,
    row: Any,
    endpoints: list[list[dict]] | None,
    *,
    append: bool = False,
) -> GraphDevice:
    """Set the physical endpoints a bus leaves from; ``None`` / ``[]`` clears them.

    A bus may leave from several places (main to FOH *and* to a recording box), so it holds a list
    of endpoints. Each endpoint is one socket for a mono bus, two (L, R) for stereo, three
    (L, R, C) for LCR; given only its first socket the rest follow on the same port. Sockets must be
    real output sockets and are exclusive: used once by one bus endpoint or one direct out. With
    ``append`` the endpoints are added to the existing ones instead of replacing them. The bus's
    output chain is kept in step (``sync_output_to_chain``).
    """
    node = await output_node_of(db, job_id, output_id)
    attrs = dict(_attrs(node))
    width = console.bus_width(_bus_mode(node))
    existing = [] if not append else list(attrs.get("out_endpoints") or [])
    new: list[dict] = []
    hardware = await job_hardware(db, job_id)
    sockets = {s["key"]: s for s in console.audio_sockets(hardware)}
    mine = {k for e in existing for k in console.endpoint_keys(e)}
    for refs in endpoints or []:
        refs = [
            {
                "device_id": str(r["device_id"]),
                "port_id": r["port_id"],
                "socket": r.get("socket") or 1,
            }
            for r in refs
        ]
        if len(refs) == 1 and width > 1:
            refs = console.expand_refs(refs[0], width)
        if len(refs) != width:
            raise HTTPException(
                status.HTTP_422_UNPROCESSABLE_CONTENT,
                f"A {_bus_mode(node)} bus needs {width} socket(s) per endpoint, got {len(refs)}",
            )
        for ref in refs:
            key = console.socket_key(ref)
            socket = sockets.get(key)
            if socket is None:
                raise HTTPException(
                    status.HTTP_422_UNPROCESSABLE_CONTENT, "No such audio socket on this job"
                )
            if socket["direction"] not in ("out", "both"):
                raise HTTPException(
                    status.HTTP_422_UNPROCESSABLE_CONTENT, f"Socket is not an output: {key}"
                )
            if key in mine:
                raise HTTPException(CONFLICT, "A socket can be used once per bus")
            mine.add(key)
        new.append({"id": str(uuid.uuid4()), "refs": refs})
    for other in await db.scalars(
        select(GraphDevice).where(
            GraphDevice.job_id == job_id,
            GraphDevice.kind.in_((audio_native.OUTPUT, audio_native.CHANNEL)),
        )
    ):
        if other.id == node.id:
            continue
        if other.kind == audio_native.OUTPUT:
            theirs = {
                k
                for e in _attrs(other).get("out_endpoints") or []
                for k in console.endpoint_keys(e)
            }
        else:
            key = console.socket_key(_attrs(other).get("direct_out"))
            theirs = {key} if key else set()
        clash = theirs & {k for e in new for k in console.endpoint_keys(e)}
        if clash:
            raise HTTPException(CONFLICT, f"That socket is already used by {other.name}")
    result = [*existing, *new]
    if result:
        attrs["out_endpoints"] = result
    else:
        attrs.pop("out_endpoints", None)
    node.attributes = attrs
    await db.flush()
    await sync_output_to_chain(db, node, row, list_id)
    return node


async def remove_output_endpoint(
    db: AsyncSession,
    job_id: uuid.UUID,
    output_id: uuid.UUID,
    list_id: uuid.UUID,
    row: Any,
    endpoint_id: str,
) -> GraphDevice:
    node = await output_node_of(db, job_id, output_id)
    attrs = dict(_attrs(node))
    kept = [e for e in attrs.get("out_endpoints") or [] if e.get("id") != endpoint_id]
    if len(kept) == len(attrs.get("out_endpoints") or []):
        raise HTTPException(status.HTTP_404_NOT_FOUND, "No such endpoint on this bus")
    if kept:
        attrs["out_endpoints"] = kept
    else:
        attrs.pop("out_endpoints", None)
    node.attributes = attrs
    await db.flush()
    await sync_output_to_chain(db, node, row, list_id)
    return node


def _label_for(socket_numbers: list[int], prefix: str = "Out") -> str:
    ordered = sorted(socket_numbers)
    if len(ordered) > 1 and ordered == list(range(ordered[0], ordered[0] + len(ordered))):
        return f"{prefix} {ordered[0]}-{ordered[-1]}"
    return f"{prefix} " + "/".join(str(n) for n in ordered)


async def sync_output_to_chain(
    db: AsyncSession, node: GraphDevice, row: Any, list_id: uuid.UUID
) -> None:
    """Bus endpoints -> output chain: one parallel branch per endpoint device.

    The chain starts at the console. The hops this made (flagged ``soft_patch``) are rebuilt from
    the endpoints: for each device an endpoint uses, a hop labelled ``Out N`` (``Out 3-4`` for a
    stereo pair) hanging off the console hop as a parallel branch, so a bus that leaves from two
    places draws two branches. Hops the user made themselves are left alone. A bus with no console
    hop yet gets one (the list's console device, created when missing) unless the only device is the
    console itself.
    """
    points = [dict(p) for p in (_attrs(node).get("points") or []) if not p.get("soft_patch")]
    endpoints = _attrs(node).get("out_endpoints") or []
    if endpoints:
        hardware = {str(d.id): d for d in await job_hardware(db, node.job_id)}
        console_node = await console_device(db, node.job_id, list_id, row)
        root = next(
            (p for p in points if str(p.get("device_id")) == str(console_node.id)), None
        ) or (points[0] if points else None)
        if root is None:
            root = {
                "point_id": str(uuid.uuid4()),
                "position": 0,
                "point_type": "mixer",
                "connector": "",
                "patch_label": "",
                "notes": "",
                "device_id": str(console_node.id),
                "revision": 1,
                "soft_patch": True,
                "parallel": False,
                "parent_id": None,
                "bus_connector": None,
            }
            points.insert(0, root)
        position = max((p.get("position") or 0 for p in points), default=0)
        for endpoint in endpoints:
            by_device: dict[str, list[dict]] = {}
            for ref in endpoint.get("refs") or []:
                by_device.setdefault(str(ref["device_id"]), []).append(ref)
            for device_id, refs in by_device.items():
                if device_id == str(root.get("device_id")):
                    continue  # the console's own sockets: the root hop already is the console
                device = hardware.get(device_id)
                port = next(
                    (
                        p
                        for p in (device.ports if device else [])
                        if p.get("id") == refs[0]["port_id"]
                    ),
                    {},
                )
                position += 1
                points.append(
                    {
                        "point_id": str(uuid.uuid4()),
                        "position": position,
                        "point_type": getattr(device, "kind", None) or "other",
                        "connector": port.get("connector") or "",
                        "patch_label": _label_for([int(r["socket"]) for r in refs]),
                        "notes": "",
                        "device_id": device_id,
                        "revision": 1,
                        "soft_patch": True,
                        "parallel": True,
                        "parent_id": root["point_id"],
                        "bus_connector": None,
                    }
                )
    await audio_native._store_points(db, node, points)
