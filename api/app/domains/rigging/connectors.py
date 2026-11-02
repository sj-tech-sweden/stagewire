"""Power connectors that can be validated in a power tree.

A node feeds its children through its outputs: each output is one connector type, with a
count of how many children or loads it can take. A child can only be plugged into an output
of the same connector type; anything else needs a distro or breakout in between.

Voltage is phase to neutral (230 V) for single-phase connectors; amps per phase are watts
divided by 230 for every node. Three-phase connectors carry 400 V between lines.
"""

from dataclasses import dataclass

PHASE_VOLTS = 230.0


@dataclass(frozen=True)
class Connector:
    key: str
    label: str
    phases: int
    amps: int
    circuits: int = 1


CONNECTORS: dict[str, Connector] = {
    c.key: c
    for c in (
        Connector("schuko", "Schuko 16 A", 1, 16),
        Connector("cee16", "CEE 16 A, 1-phase", 1, 16),
        Connector("cee16_3p", "CEE 16 A, 3-phase", 3, 16),
        Connector("cee32_3p", "CEE 32 A, 3-phase", 3, 32),
        Connector("cee63_3p", "CEE 63 A, 3-phase", 3, 63),
        Connector("cee125_3p", "CEE 125 A, 3-phase (Commando)", 3, 125),
        Connector("powercon", "powerCON 20 A", 1, 20),
        Connector("powercon_true1", "powerCON TRUE1", 1, 20),
        Connector("socapex", "Socapex 19-pin (6 × 16 A)", 1, 16, circuits=6),
        # Fixed wiring in a venue: bare wires or terminals whose rating depends on the cable
        # size, so the node must be rated by hand (amps 0 means "rate it").
        Connector("install_1p", "Fixed installation, bare wires, 1-phase", 1, 0),
        Connector("install_3p", "Fixed installation, bare wires, 3-phase", 3, 0),
    )
}


# Keys added from the shared connector kinds (see domains/connectors); replaced as a whole on each
# refresh so a deleted kind disappears. They live in CONNECTORS so the power tree sees them too.
_custom_keys: set[str] = set()


def register_custom(connectors: list[Connector]) -> None:
    for key in _custom_keys:
        CONNECTORS.pop(key, None)
    _custom_keys.clear()
    for item in connectors:
        if item.key in CONNECTORS:
            continue
        CONNECTORS[item.key] = item
        _custom_keys.add(item.key)


def known(key: str | None) -> bool:
    return key in CONNECTORS


def needs_rating(key: str | None) -> bool:
    """Installation wiring has no fixed rating: its node must be rated by hand."""
    return key in CONNECTORS and CONNECTORS[key].amps == 0


def connector(key: str) -> Connector:
    return CONNECTORS[key]


def catalog() -> list[dict]:
    return [
        {
            "key": c.key,
            "label": c.label,
            "phases": c.phases,
            "amps": c.amps,
            "circuits": c.circuits,
            "custom": c.key in _custom_keys,
        }
        for c in CONNECTORS.values()
    ]


def catalog_is_custom(key: str) -> bool:
    return key in _custom_keys
