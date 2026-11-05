"""Device-driven load for a venue's power supply (incoming -> groups -> outlets).

The supply template the venue offers is a tree of ``VenuePowerGroup`` (panels, the incoming
supply) and ``VenuePowerOutlet`` (sockets on the stage). Each group has a ``rating_amps`` that is
its *capacity* — the most it can deliver — not the load on it. The actual load is the watts of the
devices plugged into the outlets (or directly into a group), summed up the tree.

This module is the single source of truth for that computation so the venue Standard Base Rig and
the job workspace show the same over-limit check: a group is "over" when the devices beneath it
draw more amps than its breaker allows. It deliberately does not read ``rating_amps`` as a load,
which would mark every multi-outlet panel as overloaded.
"""

from __future__ import annotations

from collections import defaultdict
from collections.abc import Iterable
from dataclasses import dataclass
from uuid import UUID

# Mains voltage used to turn watts into amps (phase-to-neutral, 230 V). Mirrors
# ``app.domains.rigging.connectors.PHASE_VOLTS`` so the venue supply limits agree with the job's
# own power tree.
VOLTS = 230.0


@dataclass(frozen=True)
class VenuePowerElement:
    """One supply element (outlet or group) with the load currently drawn through it."""

    id: UUID
    watts: float
    amps: float
    over: bool


@dataclass(frozen=True)
class VenuePowerSummary:
    outlets: list[VenuePowerElement]
    groups: list[VenuePowerElement]
    incoming: VenuePowerElement | None
    total_watts: float
    total_amps: float


def _amps(watts: float) -> float:
    return watts / VOLTS


def _over(rating_amps: float | None, amps: float) -> bool:
    return rating_amps is not None and amps > rating_amps


def summarize_venue_power(
    groups: Iterable,
    outlets: Iterable,
    outlet_watts: dict[UUID, float],
    group_direct_watts: dict[UUID, float],
) -> VenuePowerSummary:
    """Aggregate device watts up the venue supply tree and flag over-limit elements.

    ``outlet_watts`` maps an outlet id to the watts drawn on it; ``group_direct_watts`` maps a
    group id to the watts drawn directly on the group junction (devices plugged into the group
    rather than one of its outlets). A group's load is its direct draw plus every outlet and nested
    subgroup beneath it, so a single overloaded device trips every breaker above it — matching how
    real distribution works. The incoming supply's load is the sum of all device watts (everything
    the venue draws).
    """
    groups = list(groups)
    outlets = list(outlets)

    group_ids = {g.id for g in groups}
    outlet_ids = {o.id for o in outlets}
    children: dict[UUID | None, list] = defaultdict(list)
    for g in groups:
        children[g.parent_id].append(g)

    # Drop attributions that point at elements which no longer exist (e.g. a deleted outlet) so a
    # stale link can never inflate a surviving panel's load.
    clean_outlet = {oid: w for oid, w in outlet_watts.items() if oid in outlet_ids}
    clean_group = {gid: w for gid, w in group_direct_watts.items() if gid in group_ids}

    def group_total(group_id: UUID) -> float:
        total = clean_group.get(group_id, 0.0)
        for outlet in outlets:
            if outlet.group_id == group_id:
                total += clean_outlet.get(outlet.id, 0.0)
        for child in children.get(group_id, []):
            total += group_total(child.id)
        return total

    group_elems = [
        VenuePowerElement(
            id=g.id,
            watts=group_total(g.id),
            amps=_amps(group_total(g.id)),
            over=_over(g.rating_amps, _amps(group_total(g.id))),
        )
        for g in groups
    ]

    outlet_elems = [
        VenuePowerElement(
            id=o.id,
            watts=clean_outlet.get(o.id, 0.0),
            amps=_amps(clean_outlet.get(o.id, 0.0)),
            over=_over(o.rating_amps, _amps(clean_outlet.get(o.id, 0.0))),
        )
        for o in outlets
    ]

    # Each device is attributed to exactly one element, so the total draw is just the sum of the
    # two attribution maps (no double counting across the tree).
    total_watts = sum(clean_outlet.values()) + sum(clean_group.values())

    incoming_group = next((g for g in groups if g.is_incoming), None)
    incoming = None
    if incoming_group is not None:
        incoming = VenuePowerElement(
            id=incoming_group.id,
            watts=total_watts,
            amps=_amps(total_watts),
            over=_over(incoming_group.rating_amps, _amps(total_watts)),
        )

    return VenuePowerSummary(
        outlets=outlet_elems,
        groups=group_elems,
        incoming=incoming,
        total_watts=total_watts,
        total_amps=_amps(total_watts),
    )
