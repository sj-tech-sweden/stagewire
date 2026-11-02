"""The id other things use for a graph node: its public id.

Cable route keys, plot element links and report layouts are keyed by the ids the legacy tables
gave their rows. Rows that came from those tables keep that id (the node's ``legacy_ref`` while
the tables back it, ``attributes.legacy_id`` after the node is made native); a node made in the
graph has no legacy id, so its public id is its own id. Everything that stores a reference to a
video node (or, later, to any migrated domain's node) stores this id, never ``GraphDevice.id``
of a legacy-backed node.
"""

import uuid

from app.domains.graph.models import GraphDevice


def public_id(node: GraphDevice) -> uuid.UUID:
    """The legacy id of a node that came from the tables, else the node's own id."""
    raw = (node.attributes or {}).get("legacy_id")
    if raw is None and node.legacy_ref:
        raw = node.legacy_ref.partition(":")[2]
    try:
        return uuid.UUID(str(raw)) if raw else node.id
    except ValueError:
        return node.id
