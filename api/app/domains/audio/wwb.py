"""Helpers for associating wireless channels with Shure Wireless Workbench.

Shure Wireless Workbench (WWB) stores coordinated RF in its ``.shw`` show file,
which is a plain UTF-8 XML document (not a zip). We support both directions:

- **Export**: the ``wireless_workbench`` console exporter turns the list's wireless
  channels (those with ``input_type == 'wireless'``) into a ``.shw`` show file whose
  coordinated channels carry the frequency (in kHz), group/channel and name, so the
  file can be opened back in WWB or re-imported into Stagewire.
- **Import**: a ``.shw`` show file is parsed here and matched to the job's existing
  wireless channels by name (channel name, pack or source label), falling back to
  channel number + source, so the coordinated frequencies land on the right channels.

Frequencies in a ``.shw`` are integers in **kHz**; we divide by 1000 to store MHz.
The historical free-text ``wireless_frequency`` string is parsed on read for
backwards compatibility and removed by a migration.
"""

import re
import xml.etree.ElementTree as ET
from xml.etree.ElementTree import Element

# A number with an optional decimal point or comma (European decimals).
_NUMBER_RE = re.compile(r"(\d+(?:[.,]\d+)?)")


def parse_mhz(value: object) -> float | None:
    """Pull a frequency in MHz out of a WWB / legacy frequency string.

    Accepts ``"518.125 MHz"``, ``"606,250"``, ``"CH 12 (518.3MHz)"`` and returns
    ``518.125`` / ``606.25`` / ``518.3``. Values above 1000 MHz are not plausible
    for the UHF/1.2 GHz bands these tools coordinate, so they are ignored unless
    they are explicitly tagged ``MHz``.
    """
    if value is None:
        return None
    text = str(value).strip()
    if not text:
        return None
    tagged = re.search(r"(\d+(?:[.,]\d+)?)\s*mhz", text, re.IGNORECASE)
    parsed = _to_float(tagged.group(1)) if tagged else None
    if parsed is not None:
        return parsed
    match = _NUMBER_RE.search(text)
    if match:
        candidate = _to_float(match.group(1))
        if candidate is not None and candidate <= 1000:
            return candidate
    return None


def _to_float(value: str) -> float | None:
    try:
        return float(str(value).replace(",", "."))
    except (ValueError, TypeError):
        return None


def normalize_wireless_attributes(attributes: dict | None) -> dict:
    """Return the structured wireless fields, converting a legacy ``wireless_frequency`` string.

    Used by the read models so unmigrated rows (and the SQLite test DB, which never
    runs Alembic) still expose ``wireless_frequency_mhz``.
    """
    attrs = dict(attributes or {})
    fields = {
        "wireless_frequency_mhz": attrs.get("wireless_frequency_mhz"),
        "wireless_group": attrs.get("wireless_group"),
        "wireless_channel": attrs.get("wireless_channel"),
    }
    legacy = attrs.get("wireless_frequency")
    if legacy and fields["wireless_frequency_mhz"] is None:
        fields["wireless_frequency_mhz"] = parse_mhz(legacy)
    return fields


def _text(element: Element | None) -> str | None:
    if element is None or element.text is None:
        return None
    return element.text.strip()


def _parent_map(root: Element) -> dict[Element, Element | None]:
    """Map every element to its direct parent (ElementTree does not track parents)."""
    return {child: parent for parent in root.iter() for child in parent}


def _parse_gr_ch(value: str | None) -> tuple[str | None, str | None]:
    """Parse a WWB group/channel string into ``(group, channel)``.

    Handles both ``"G:50 Ch:12"`` (``<gr_ch>``) and ``"50,12"``
    (``<group_channel>``); unset markers such as ``"G:-- Ch:--"`` or ``"--,--"``
    yield ``(None, None)``.
    """
    if not value:
        return None, None
    explicit = re.search(r"G:\s*(\d+)\s*Ch:\s*(\d+)", value)
    if explicit:
        return explicit.group(1), explicit.group(2)
    comma = re.search(r"(\d+)\s*,\s*(\d+)", value)
    if comma:
        return comma.group(1), comma.group(2)
    return None, None


def parse_wwb_show_file(xml_text: str) -> list[dict]:
    """Parse a Shure Wireless Workbench ``.shw`` show file into wireless rows.

    Returns a list of dicts, each with some of: ``name``, ``wireless_frequency_mhz``,
    ``wireless_group``, ``wireless_channel``, ``wireless_pack``, ``channel_number``.
    Only channels that carry a tuned frequency (``<frequency>``) are returned; the many
    TV-avoidance ``<channel>`` entries in a show file have no ``<frequency>`` and are
    skipped. Frequencies are integers in kHz and are converted to MHz.
    """
    root = ET.fromstring(xml_text)
    parents = _parent_map(root)
    rows: list[dict] = []
    for channel in root.iter("channel"):
        freq_el = channel.find("frequency")
        khz = _to_float(_text(freq_el)) if freq_el is not None else None
        if khz is None:
            continue
        name = _text(channel.find("channel_name")) or ""
        group, chan = _parse_gr_ch(
            _text(channel.find("gr_ch")) or _text(channel.find("group_channel"))
        )
        # Walk up to the enclosing <device> for model/band context.
        device = None
        node = parents.get(channel)
        while node is not None and node.tag != "device":
            node = parents.get(node)
        if node is not None and node.tag == "device":
            device = node
        model = _text(device.find("model")) if device is not None else None
        band = _text(device.find("band")) if device is not None else None
        channel_number = None
        if device is not None:
            for index, sibling in enumerate(device.findall("channel"), start=1):
                if sibling is channel:
                    channel_number = index
                    break
        pack = f"{model} {band}".strip() if (model or band) else None
        if not name and pack and channel_number:
            name = f"{pack} {channel_number}"
        rows.append(
            {
                "name": name or None,
                "wireless_frequency_mhz": round(khz / 1000.0, 3),
                "wireless_group": group,
                "wireless_channel": chan,
                "wireless_pack": pack,
                "channel_number": channel_number,
            }
        )
    return rows


def match_wireless_rows(channels: list, rows: list[dict]) -> tuple[list[tuple], list[dict]]:
    """Match parsed WWB rows to existing wireless channels.

    Returns ``(matched, unmatched)`` where ``matched`` is a list of
    ``(channel, row)`` for channels whose ``input_type == 'wireless'`` and whose
    name (pack or source label) matches a row's ``name`` or ``wireless_pack``,
    falling back to channel number + source. ``unmatched`` is the list of rows that
    matched no channel.
    """
    by_name: dict[str, list] = {}
    by_number_source: dict[tuple, list] = {}
    for channel in channels:
        if getattr(channel, "input_type", None) != "wireless":
            continue
        for field in ("wireless_pack", "source_label"):
            key = (getattr(channel, field, None) or "").strip().lower()
            if key:
                by_name.setdefault(key, []).append(channel)
        number = getattr(channel, "channel_number", None)
        source = (getattr(channel, "source_label", None) or "").strip().lower()
        if number is not None:
            by_number_source.setdefault((number, source), []).append(channel)

    matched: list[tuple] = []
    seen_channel_ids = set()
    unmatched: list[dict] = []
    for row in rows:
        candidates: list = []
        for field in ("name", "wireless_pack"):
            key = (row.get(field) or "").strip().lower()
            if key:
                candidates.extend(by_name.get(key, []))
        if not candidates and row.get("channel_number") is not None:
            candidates = by_number_source.get(
                (row["channel_number"], (row.get("source_label") or "").strip().lower()),
                [],
            )
        channel = next((c for c in candidates if id(c) not in seen_channel_ids), None)
        if channel is None:
            unmatched.append(row)
            continue
        seen_channel_ids.add(id(channel))
        matched.append((channel, row))
    return matched, unmatched


def wireless_frequency_summary(mhz: float | None, group: str | None, channel: str | None) -> str:
    """A human-readable frequency line for reports (e.g. ``"518.125 MHz · G50/12"``)."""
    parts: list[str] = []
    if mhz is not None:
        parts.append(f"{mhz} MHz")
    if group or channel:
        parts.append("/".join(p for p in (group, channel) if p))
    return " · ".join(parts)
