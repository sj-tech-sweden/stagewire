from collections import deque
from collections.abc import Iterable, Mapping
from dataclasses import dataclass, field
from typing import Any

SIGNALS = ("audio", "video", "dmx", "power", "data", "link")
PHASES = ("L1", "L2", "L3")

CONNECTOR_COMPAT: dict[str, frozenset[str]] = {
    "socapex19": frozenset({"socapex19"}),
    "xlr3": frozenset({"xlr3"}),
    "xlr5": frozenset({"xlr5", "xlr3"}),
    "sdi": frozenset({"sdi"}),
    "hdmi": frozenset({"hdmi"}),
    "rj45": frozenset({"rj45", "ethercon"}),
    "powercon": frozenset({"powercon"}),
    "schuko": frozenset({"schuko"}),
}


def connectors_compatible(src: str | None, dst: str | None) -> bool:
    if not src or not dst:
        return True
    a, b = src.lower(), dst.lower()
    if a == b:
        return True
    return b in CONNECTOR_COMPAT.get(a, frozenset()) or a in CONNECTOR_COMPAT.get(b, frozenset())


@dataclass(frozen=True)
class Issue:
    code: str
    message: str
    edge_id: str | None = None
    device_id: str | None = None


@dataclass
class Hop:
    edge: Mapping[str, Any]
    device_id: str
    depth: int


@dataclass
class Trace:
    root: str
    hops: list[Hop] = field(default_factory=list)
    truncated: bool = False


# Issues that mean the edge cannot exist at all: it names a port the device does not have, a device
# that is not there, or a cable from an input / to an output. "Connect anyway" can accept a
# connector or capacity mismatch, but never these, since a cable saved against a missing port
# shows up in the signal flow under a port name that is not on the device.
HARD_ISSUES = frozenset({"unknown_port", "missing_device", "direction"})


def blocks_forced(issues: Iterable[Issue]) -> bool:
    return any(issue.code in HARD_ISSUES for issue in issues)


def find_port(device: Mapping[str, Any], port_id: str) -> Mapping[str, Any] | None:
    return next((p for p in device.get("ports") or [] if p.get("id") == port_id), None)


def would_create_cycle(edges: Iterable[Mapping[str, Any]], src: str, dst: str) -> bool:
    adjacency: dict[str, list[str]] = {}
    for edge in edges:
        adjacency.setdefault(str(edge["src_device_id"]), []).append(str(edge["dst_device_id"]))
    if src == dst:
        return True
    seen = {dst}
    queue = deque([dst])
    while queue:
        node = queue.popleft()
        for nxt in adjacency.get(node, []):
            if nxt == src:
                return True
            if nxt not in seen:
                seen.add(nxt)
                queue.append(nxt)
    return False


def trace(
    edges: Iterable[Mapping[str, Any]],
    root: str,
    direction: str,
    *,
    signal: str | None = None,
    max_depth: int = 64,
) -> Trace:
    forward = direction == "downstream"
    near, far = (
        ("src_device_id", "dst_device_id") if forward else ("dst_device_id", "src_device_id")
    )
    index: dict[str, list[Mapping[str, Any]]] = {}
    for edge in edges:
        if (signal and edge["signal"] != signal) or (not signal and edge["signal"] == "link"):
            continue
        index.setdefault(str(edge[near]), []).append(edge)
    result = Trace(root=root)
    seen = {root}
    queue = deque([(root, 0)])
    while queue:
        node, depth = queue.popleft()
        for edge in index.get(node, []):
            nxt = str(edge[far])
            if nxt in seen:
                continue
            if depth + 1 > max_depth:
                result.truncated = True
                continue
            seen.add(nxt)
            result.hops.append(Hop(edge=edge, device_id=nxt, depth=depth + 1))
            queue.append((nxt, depth + 1))
    return result


def validate_edge(
    edge: Mapping[str, Any],
    src: Mapping[str, Any] | None,
    dst: Mapping[str, Any] | None,
    siblings: Iterable[Mapping[str, Any]] = (),
) -> list[Issue]:
    edge_id = str(edge.get("id")) if edge.get("id") else None
    if src is None or dst is None:
        return [Issue("missing_device", "Edge references a missing device", edge_id)]
    if edge["signal"] == "link":
        return []
    issues: list[Issue] = []

    def add(code: str, message: str) -> None:
        issues.append(Issue(code, message, edge_id))

    if edge["signal"] not in SIGNALS:
        add("unknown_signal", f"Unknown signal type {edge['signal']!r}")
    if edge.get("phase") and (edge["signal"] != "power" or edge["phase"] not in PHASES):
        add("bad_phase", "Phase is only valid for power edges and must be L1, L2 or L3")
    sport = find_port(src, edge["src_port"])
    dport = find_port(dst, edge["dst_port"])
    if sport is None:
        add("unknown_port", f"{src['name']} has no port {edge['src_port']!r}")
    if dport is None:
        add("unknown_port", f"{dst['name']} has no port {edge['dst_port']!r}")
    if sport is None or dport is None:
        return issues
    if sport.get("direction") != "out":
        add("direction", f"{src['name']}:{sport['id']} is not an output")
    if dport.get("direction") != "in":
        add("direction", f"{dst['name']}:{dport['id']} is not an input")
    for port, owner in ((sport, src), (dport, dst)):
        if port.get("signal") and port["signal"] != edge["signal"]:
            add("signal_mismatch", f"{owner['name']}:{port['id']} carries {port['signal']}")
    if not connectors_compatible(sport.get("connector"), dport.get("connector")):
        add(
            "connector_mismatch",
            f"{sport.get('connector')} cannot mate with {dport.get('connector')}",
        )
    channels = int(edge.get("channels") or 1)
    for port, owner in ((sport, src), (dport, dst)):
        capacity = port.get("channels")
        if capacity is not None and channels > int(capacity):
            add(
                "channel_count",
                f"{owner['name']}:{port['id']} has {capacity} channels, edge needs {channels}",
            )
    others = [e for e in siblings if str(e.get("id")) != str(edge.get("id"))]
    on_dst = [
        e
        for e in others
        if str(e["dst_device_id"]) == str(dst["id"]) and e["dst_port"] == edge["dst_port"]
    ]
    dst_cap = dport.get("channels")
    if dst_cap is None:
        if len(on_dst) >= int(dport.get("max_connections") or 1):
            add("port_in_use", f"{dst['name']}:{edge['dst_port']} already has a source")
    elif sum(int(e.get("channels") or 1) for e in on_dst) + channels > int(dst_cap):
        add("port_in_use", f"{dst['name']}:{edge['dst_port']} has no free channels left")
    on_src = [
        e
        for e in others
        if str(e["src_device_id"]) == str(src["id"]) and e["src_port"] == edge["src_port"]
    ]
    src_cap = sport.get("channels")
    if src_cap is not None:
        if sum(int(e.get("channels") or 1) for e in on_src) + channels > int(src_cap):
            add("port_in_use", f"{src['name']}:{edge['src_port']} has no free channels left")
    elif len(on_src) >= int(sport.get("max_connections") or 1):
        add("port_in_use", f"{src['name']}:{edge['src_port']} is at its connection limit")
    return issues


def phase_loads(
    devices: Mapping[str, Mapping[str, Any]], edges: Iterable[Mapping[str, Any]]
) -> dict[str, float]:
    loads = dict.fromkeys(PHASES, 0.0)
    for edge in edges:
        if edge["signal"] != "power" or edge.get("phase") not in loads:
            continue
        dst = devices.get(str(edge["dst_device_id"]))
        loads[edge["phase"]] += float(((dst or {}).get("attributes") or {}).get("power_w") or 0)
    return loads


VOLTS = 230.0
DEFAULT_PHASE_AMPS = 16.0


def phase_limit_w(devices: Mapping[str, Mapping[str, Any]]) -> float:
    """Per-phase wattage the job's power sources can deliver (amps per phase x 230 V).

    Source ratings add up; with no rated source the limit falls back to a 16 A feed.
    """
    amps = sum(
        float((d.get("attributes") or {}).get("rating_amps") or 0)
        for d in devices.values()
        if d.get("domain") == "power" and d.get("kind") == "source"
    )
    return (amps or DEFAULT_PHASE_AMPS) * VOLTS
