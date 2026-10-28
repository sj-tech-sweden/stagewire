"""Load, amps and status for a power tree (source, distros, breakouts and loads).

Pure functions over plain values. The tree is evaluated from the sources down:

- A node is powered when it is a source and active, or when its parent is powered and the
  node itself is active. A non-source node with no parent is never powered.
- Each entity under a node (a load, or a child node) adds its watts to a phase: the phase
  of the output it plugs into, or all three phases evenly when that output has no phase.
- Amps per phase are watts on that phase over 230 V.
- A node's rating is its own rating, or the amps of its feed connector when unset. Status is
  "ok" below 80 % of the rating, "warn" from 80 %, and "over" above 100 %.
- A node with no power is "unpowered"; its loads inherit that.
"""

from dataclasses import dataclass, field

from app.domains.rigging.connectors import CONNECTORS, PHASE_VOLTS

PHASES = ("L1", "L2", "L3")
WARN_AT = 0.8


@dataclass(frozen=True)
class Output:
    connector: str
    count: int
    phase: str | None = None


@dataclass(frozen=True)
class Node:
    id: str
    kind: str  # "source" | "distro" | "breakout"
    name: str
    parent_id: str | None
    feed_connector: str
    phase: str | None
    outputs: tuple[Output, ...] = ()
    rating_amps: float | None = None
    active: bool = True


@dataclass(frozen=True)
class Load:
    id: str
    label: str
    node_id: str | None
    connector: str
    watts: float | None
    kind: str = "fixture"


@dataclass
class Evaluation:
    nodes: dict[str, dict] = field(default_factory=dict)
    loads: dict[str, dict] = field(default_factory=dict)
    errors: list[str] = field(default_factory=list)


def _rating(node: Node) -> float:
    if node.rating_amps:
        return node.rating_amps
    feed = CONNECTORS.get(node.feed_connector)
    return float(feed.amps) if feed else 0.0


def _status(amps: float, rating: float) -> str:
    if rating <= 0:
        return "ok"
    ratio = amps / rating
    if ratio > 1:
        return "over"
    if ratio >= WARN_AT:
        return "warn"
    return "ok"


def _output_for(parent: Node, connector: str) -> Output | None:
    return next((o for o in parent.outputs if o.connector == connector), None)


def evaluate(nodes: list[Node], loads: list[Load]) -> Evaluation:
    result = Evaluation()
    by_id = {n.id: n for n in nodes}
    children: dict[str, list[Node]] = {}
    for node in nodes:
        if node.parent_id:
            children.setdefault(node.parent_id, []).append(node)

    # Structural checks: each child must plug into a declared output, and no output may be
    # used by more children and loads than it has.
    used: dict[tuple[str, str], int] = {}
    for node in nodes:
        if node.kind != "source" and node.parent_id is None:
            result.errors.append(f"{node.name}: not connected to a source")
        if node.parent_id:
            parent = by_id.get(node.parent_id)
            if parent is None:
                result.errors.append(f"{node.name}: parent is missing")
                continue
            if _output_for(parent, node.feed_connector) is None:
                result.errors.append(
                    f"{node.name}: {node.feed_connector} is not an output of {parent.name}"
                )
            else:
                key = (parent.id, node.feed_connector)
                used[key] = used.get(key, 0) + 1
    for load in loads:
        if load.node_id is None:
            continue
        parent = by_id.get(load.node_id)
        if parent is None:
            continue
        if _output_for(parent, load.connector) is None:
            result.errors.append(
                f"{load.label}: {load.connector} is not an output of {parent.name}"
            )
        else:
            key = (parent.id, load.connector)
            used[key] = used.get(key, 0) + 1
    for (node_id, connector), count in used.items():
        output = _output_for(by_id[node_id], connector)
        if output and count > output.count:
            result.errors.append(
                f"{by_id[node_id].name}: {connector} has {count} in use, {output.count} available"
            )

    powered: dict[str, bool] = {}

    def is_powered(node: Node, seen: frozenset[str] = frozenset()) -> bool:
        if node.id in powered:
            return powered[node.id]
        if node.id in seen:
            return False
        if node.kind == "source":
            value = node.active
        elif node.parent_id and node.parent_id in by_id:
            value = node.active and is_powered(by_id[node.parent_id], seen | {node.id})
        else:
            value = False
        powered[node.id] = value
        return value

    def spread(total: float, phase: str | None) -> dict[str, float]:
        if phase in PHASES:
            return {p: (total if p == phase else 0.0) for p in PHASES}
        return dict.fromkeys(PHASES, total / 3)

    def add(into: dict[str, float], part: dict[str, float]) -> None:
        for p in PHASES:
            into[p] += part[p]

    totals: dict[str, dict[str, float]] = {}

    def total_of(node: Node, guard: frozenset[str] = frozenset()) -> dict[str, float]:
        if node.id in totals:
            return totals[node.id]
        acc = dict.fromkeys(PHASES, 0.0)
        if node.id in guard:
            return acc
        for load in loads:
            if load.node_id != node.id:
                continue
            output = _output_for(node, load.connector)
            add(acc, spread(load.watts or 0.0, output.phase if output else None))
        for child in children.get(node.id, []):
            output = _output_for(node, child.feed_connector)
            add(
                acc,
                spread(
                    sum(total_of(child, guard | {node.id}).values()),
                    output.phase if output else None,
                ),
            )
        totals[node.id] = acc
        return acc

    for node in nodes:
        is_powered(node)
    for node in nodes:
        watts = total_of(node)
        amps = {p: watts[p] / PHASE_VOLTS for p in PHASES}
        peak = max(amps.values())
        rating = _rating(node)
        status = "unpowered" if not powered[node.id] else _status(peak, rating)
        result.nodes[node.id] = {
            "id": node.id,
            "name": node.name,
            "kind": node.kind,
            "parent_id": node.parent_id,
            "feed_connector": node.feed_connector,
            "powered": powered[node.id],
            "watts": {p: round(watts[p], 1) for p in PHASES},
            "amps": {p: round(amps[p], 2) for p in PHASES},
            "rating_amps": rating,
            "percent": round(peak / rating * 100, 1) if rating else None,
            "status": status,
        }
    for load in loads:
        parent_powered = load.node_id is not None and powered.get(load.node_id, False)
        result.loads[load.id] = {
            "id": load.id,
            "label": load.label,
            "powered": bool(parent_powered),
            "status": "ok" if parent_powered else "unpowered",
        }
    return result
