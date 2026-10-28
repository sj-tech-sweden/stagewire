"""Read a fixture patch from a CSV export or an MVR (My Virtual Rig) file.

Both readers return plain dicts shaped like ``FixtureCreate`` plus any rows that could not
be read as error messages. Nothing here touches the database.

CSV: the first line is the header. Headers are matched case-insensitively against the
aliases in ``CSV_HEADERS``; unknown columns are ignored. ``;`` or ``,`` may separate cells.

MVR: ``GeneralSceneDescription.xml`` lists the fixtures. A fixture's channel footprint and
fixture type come from the GDTF file it names (``GDTFSpec``), found in the same archive.
"""

import csv
import io
import os
import re
import zipfile
from typing import Any
from xml.etree import ElementTree

CSV_HEADERS = {
    "name": "device_name",
    "device": "device_name",
    "device name": "device_name",
    "fixture name": "device_name",
    "universe": "universe",
    "address": "dmx_address",
    "dmx address": "dmx_address",
    "dmx": "dmx_address",
    "fixture type": "fixture_type",
    "type": "fixture_type",
    "channel mode": "channel_mode",
    "mode": "channel_mode",
    "footprint": "footprint",
    "channels": "footprint",
    "location": "location",
    "location/truss position": "location",
    "location / truss position": "location",
    "truss position": "location",
    "truss": "location",
    "gel": "gel",
    "gel/color": "gel",
    "gel / color": "gel",
    "color": "gel",
    "purpose": "purpose",
    "function": "purpose",
    "notes": "notes",
}
INT_KEYS = {"universe", "dmx_address", "footprint"}
DMX_CHANNELS_PER_UNIVERSE = 512


def _text(value: Any) -> str:
    return "" if value is None else str(value).strip()


def _int(value: str) -> int:
    number = int(float(value))
    if number < 1:
        raise ValueError(value)
    return number


def _decode(data: bytes) -> str:
    try:
        return data.decode("utf-8-sig")
    except UnicodeDecodeError:
        return data.decode("latin-1")


def parse_csv(data: bytes) -> tuple[list[dict], list[str]]:
    text = _decode(data)
    first_line = next((line for line in text.splitlines() if line.strip()), "")
    delimiter = ";" if first_line.count(";") > first_line.count(",") else ","
    reader = csv.reader(io.StringIO(text), delimiter=delimiter)
    try:
        header = next(reader)
    except StopIteration:
        return [], []
    keys = [CSV_HEADERS.get(re.sub(r"\s+", " ", _text(h)).lower()) for h in header]
    rows: list[dict] = []
    errors: list[str] = []
    for number, cells in enumerate(reader, start=2):
        if not any(_text(c) for c in cells):
            continue
        row: dict[str, Any] = {}
        try:
            for key, cell in zip(keys, cells, strict=False):
                value = _text(cell)
                if key is None or not value:
                    continue
                row[key] = _int(value) if key in INT_KEYS else value
        except ValueError:
            errors.append(f"Line {number}: a number is not valid")
            continue
        rows.append(row)
    return rows, errors


def parse_address(text: str) -> tuple[int | None, int | None]:
    """``universe.address`` or an absolute DMX number (1 is universe 1, address 1)."""
    text = _text(text)
    try:
        if "." in text:
            universe, address = text.split(".", 1)
            return int(universe), int(address)
        absolute = int(text)
    except ValueError:
        return None, None
    if absolute < 1:
        return None, None
    return (absolute - 1) // DMX_CHANNELS_PER_UNIVERSE + 1, (
        absolute - 1
    ) % DMX_CHANNELS_PER_UNIVERSE + 1


def _local(tag: str) -> str:
    return tag.split("}")[-1]


def _child_text(node: ElementTree.Element, name: str) -> str:
    for child in node:
        if _local(child.tag) == name:
            return _text(child.text)
    return ""


def _translation_m(matrix: str) -> tuple[float, float, float] | None:
    groups = re.findall(r"\{([^}]*)\}", matrix)
    if len(groups) < 4:
        return None
    try:
        x, y, z = (float(v) for v in groups[3].split(",")[:3])
    except ValueError:
        return None
    return x / 1000, y / 1000, z / 1000


class _GdtfLookup:
    """Fixture type name and every DMX mode (name to channel footprint) of a GDTF file,
    read from the MVR archive."""

    def __init__(self, archive: zipfile.ZipFile) -> None:
        self._archive = archive
        self._members = {os.path.basename(n).lower(): n for n in archive.namelist()}
        self._cache: dict[str, tuple[str | None, dict[str, int]]] = {}

    def _member(self, spec: str) -> str | None:
        base = spec.lower()
        return self._members.get(base) or self._members.get(f"{base}.gdtf")

    def lookup(self, spec: str) -> tuple[str | None, dict[str, int]]:
        if spec not in self._cache:
            self._cache[spec] = self._read(spec)
        return self._cache[spec]

    def _read(self, spec: str) -> tuple[str | None, dict[str, int]]:
        member = self._member(spec) if spec else None
        if member is None:
            return None, {}
        try:
            with zipfile.ZipFile(io.BytesIO(self._archive.read(member))) as gdtf:
                description = next(
                    (n for n in gdtf.namelist() if n.lower() == "description.xml"), None
                )
                if description is None:
                    return None, {}
                root = ElementTree.fromstring(gdtf.read(description))
        except (zipfile.BadZipFile, ElementTree.ParseError, KeyError):
            return None, {}
        fixture_type = None
        modes: dict[str, int] = {}
        for node in root.iter():
            tag = _local(node.tag)
            if tag == "FixtureType" and fixture_type is None:
                fixture_type = node.get("Name") or None
            if tag == "DMXMode" and node.get("Name"):
                footprint = sum(1 for c in node.iter() if _local(c.tag) == "DMXChannel")
                if footprint:
                    modes[node.get("Name")] = footprint
        return fixture_type, modes


def parse_mvr(data: bytes) -> tuple[list[dict], list[str]]:
    try:
        archive = zipfile.ZipFile(io.BytesIO(data))
    except zipfile.BadZipFile as exc:
        raise ValueError("The file is not an MVR archive") from exc
    with archive:
        scene = next(
            (n for n in archive.namelist() if n.lower() == "generalscenedescription.xml"),
            None,
        )
        if scene is None:
            raise ValueError("The MVR archive has no GeneralSceneDescription.xml")
        try:
            root = ElementTree.fromstring(archive.read(scene))
        except ElementTree.ParseError as exc:
            raise ValueError("GeneralSceneDescription.xml is not valid XML") from exc
        positions = {
            node.get("uuid"): node.get("name")
            for node in root.iter()
            if _local(node.tag) == "Position" and node.get("name")
        }
        gdtf = _GdtfLookup(archive)
        rows = [
            _fixture_row(node, positions, gdtf)
            for node in root.iter()
            if _local(node.tag) == "Fixture"
        ]
    return rows, []


def _fixture_row(node: ElementTree.Element, positions: dict[str, str], gdtf: _GdtfLookup) -> dict:
    spec = _child_text(node, "GDTFSpec")
    mode = _child_text(node, "GDTFMode")
    fixture_type, modes = gdtf.lookup(spec) if spec else (None, {})
    footprint = modes.get(mode)

    addresses = [
        a for c in node if _local(c.tag) == "Addresses" for a in c if _local(a.tag) == "Address"
    ]
    primary = next((a for a in addresses if a.get("break", "0") == "0"), None)
    if primary is None and addresses:
        primary = addresses[0]
    universe, dmx_address = parse_address(primary.text if primary is not None else "")

    position_ref = _child_text(node, "Position")
    matrix = _child_text(node, "Matrix")
    location = positions.get(position_ref, "")
    if not location and matrix:
        point = _translation_m(matrix)
        if point is not None:
            location = "x {:.2f} y {:.2f} z {:.2f} m".format(*point)

    name = _text(node.get("name")) or _child_text(node, "FixtureID") or spec
    row = {
        "type_modes": modes,
        "device_name": name,
        "universe": universe,
        "dmx_address": dmx_address,
        "fixture_type": fixture_type or spec,
        "channel_mode": mode,
        "footprint": footprint,
        "location": location,
        "purpose": _child_text(node, "Function"),
    }
    return {key: value for key, value in row.items() if value not in (None, "", {})}
