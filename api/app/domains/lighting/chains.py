"""Signal-flow trees for DMX universes.

A universe's steps form a tree: each step's parent is the step it takes DMX from, so a
splitter can feed several fixtures and a fixture can pass DMX on. Trees are built here from
the flat step rows, so the router and tests share one shape.
"""

from typing import Any


def build_tree(steps: list[Any], labels: dict[str, str]) -> list[dict]:
    """Nested nodes for the steps of one universe, ordered by position.

    ``steps`` are rows with id, parent_id, position, device_id, fixture_id, in_port,
    out_port, connector and notes. ``labels`` maps a step id to its display name.
    """
    children: dict[str | None, list[Any]] = {}
    for step in steps:
        parent = str(step.parent_id) if step.parent_id else None
        children.setdefault(parent, []).append(step)
    for group in children.values():
        group.sort(key=lambda s: s.position)

    def node(step: Any) -> dict:
        return {
            "id": str(step.id),
            "kind": "fixture" if step.fixture_id else "device",
            "label": labels.get(str(step.id), ""),
            "in_port": step.in_port,
            "out_port": step.out_port,
            "connector": step.connector,
            "notes": step.notes,
            "children": [node(child) for child in children.get(str(step.id), [])],
        }

    return [node(step) for step in children.get(None, [])]


def descendants(steps: list[Any], step_id: str) -> set[str]:
    """Ids of the steps below ``step_id``, so a step cannot be placed under its own branch."""
    children: dict[str, list[str]] = {}
    for step in steps:
        if step.parent_id:
            children.setdefault(str(step.parent_id), []).append(str(step.id))
    found: set[str] = set()
    stack = [step_id]
    while stack:
        for child in children.get(stack.pop(), []):
            if child not in found:
                found.add(child)
                stack.append(child)
    return found
