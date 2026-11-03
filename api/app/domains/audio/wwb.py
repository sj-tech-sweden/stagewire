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

import copy
import re
import xml.etree.ElementTree as ET
from pathlib import Path
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
    # A tuned channel appears twice in a show file: once inside its <device> (carrying model/band
    # and channel number) and once as a coordination view under <channel_management>. Both carry
    # the frequency, so we collect every frequency-bearing channel and reconcile below.
    raw_rows: list[tuple[dict, bool]] = []
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
        from_device = node is not None and node.tag == "device"
        if from_device:
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
        raw_rows.append(
            (
                {
                    "name": name or None,
                    "wireless_frequency_mhz": round(khz / 1000.0, 3),
                    "wireless_group": group,
                    "wireless_channel": chan,
                    "wireless_pack": pack,
                    "channel_number": channel_number,
                },
                from_device,
            )
        )
    # A tuned channel appears twice in a show file: once inside its <device> (carrying model/band
    # and channel number) and once as a coordination view under <channel_management>. When the file
    # has device channels we keep only those — they are authoritative and distinct (one per
    # physically-tuned channel) — and drop the coordination-view duplicates. Show files that carry
    # no <device> (only a coordination list) keep those channels as-is.
    device_rows = [row for row, from_device in raw_rows if from_device]
    if device_rows:
        return device_rows
    return [row for row, from_device in raw_rows if not from_device]


def match_wireless_rows(
    channels: list, rows: list[dict], positional: bool = True
) -> tuple[list[tuple], list[dict], str]:
    """Match parsed WWB rows to existing wireless channels.

    Returns ``(matched, unmatched, method)`` where ``matched`` is a list of
    ``(channel, row)``. Channels whose ``input_type == 'wireless'`` are matched by
    name (pack or source label, or the row's device model) and, when a row carries a
    channel number, by number + source.

    WWB show files frequently leave ``channel_name`` at its default ("Shure"), so a
    name match finds nothing. When no row matches by name we fall back to a positional
    match (the n-th tuned channel to the n-th wireless channel by channel number),
    which ``method`` reports as ``"order"`` so the caller can warn the user to verify.
    ``method`` is ``"name"`` when at least one row matched by name/number, ``"order"``
    when only the positional fallback applied, and ``"none"`` when nothing matched.
    """
    wireless = [c for c in channels if getattr(c, "input_type", None) == "wireless"]
    by_name: dict[str, list] = {}
    by_number_source: dict[tuple, list] = {}
    for channel in wireless:
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
    seen_row_ids = set()
    unmatched: list[dict] = []
    matched_by_name = False
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
        seen_row_ids.add(id(row))
        matched.append((channel, row))
        matched_by_name = True

    if positional and not matched_by_name and unmatched:
        wireless_sorted = sorted(wireless, key=lambda c: getattr(c, "channel_number", 0) or 0)
        rows_sorted = sorted(unmatched, key=lambda r: r.get("channel_number") or 0)
        for channel, row in zip(wireless_sorted, rows_sorted, strict=False):
            if id(channel) in seen_channel_ids:
                continue
            seen_channel_ids.add(id(channel))
            seen_row_ids.add(id(row))
            matched.append((channel, row))

    unmatched = [r for r in unmatched if id(r) not in seen_row_ids]
    method = "none" if not matched else ("name" if matched_by_name else "order")
    return matched, unmatched, method


def wireless_frequency_summary(mhz: float | None, group: str | None, channel: str | None) -> str:
    """A human-readable frequency line for reports (e.g. ``"518.125 MHz · G50/12"``)."""
    parts: list[str] = []
    if mhz is not None:
        parts.append(f"{mhz} MHz")
    if group or channel:
        parts.append("/".join(p for p in (group, channel) if p))
    return " · ".join(parts)


def _gr_ch_markup(group: str | None, channel: str | None) -> tuple[str, str]:
    """Render WWB group/channel markers for an export, using the unset form when empty."""
    if group and channel:
        return f"G:{group} Ch:{channel}", f"{group},{channel}"
    return "G:-- Ch:--", "--,--"


def _set_text(element: Element, tag: str, value: str) -> None:
    """Set (creating if absent) a child element's text under ``element``."""
    child = element.find(tag)
    if child is None:
        child = ET.SubElement(element, tag)
    child.text = value


def _channel_display_name(channel) -> str:
    return (
        getattr(channel, "source_label", None)
        or getattr(channel, "wireless_pack", None)
        or f"Channel {getattr(channel, 'channel_number', None) or '?'}"
    )


def apply_stagewire_to_show_file(template_xml: str, channels: list) -> str:
    """Return ``template_xml`` with Stagewire's coordinated frequencies written back.

    The tuned channels are matched to the show file's channels (by name, falling back to
    order) and each show-file channel has its ``<frequency>``/``<channel_name>``/group
    markers, plus the parallel ``coordinated_data_root/mic_channels/freq_entry`` values,
    updated. Channels that do not match a Stagewire wireless channel are left untouched.
    """
    root = ET.fromstring(template_xml)

    device_channels = [c for c in root.iter("channel") if c.find("frequency") is not None]
    freq_entries = root.findall(".//coordinated_data_root/mic_channels/freq_entry")
    rows = parse_wwb_show_file(template_xml)

    matched, _unmatched, _method = match_wireless_rows(channels, rows)
    row_to_channel = {id(row): channel for channel, row in matched}

    for index, element in enumerate(device_channels):
        row = rows[index] if index < len(rows) else None
        channel = row_to_channel.get(id(row)) if row is not None else None
        if channel is None:
            continue
        mhz = getattr(channel, "wireless_frequency_mhz", None)
        khz = int(round(mhz * 1000)) if mhz is not None else 0
        _set_text(element, "frequency", str(khz))
        _set_text(element, "channel_name", _channel_display_name(channel))
        gr_ch, group_channel = _gr_ch_markup(
            getattr(channel, "wireless_group", None),
            getattr(channel, "wireless_channel", None),
        )
        _set_text(element, "gr_ch", gr_ch)
        _set_text(element, "group_channel", group_channel)

    for index, entry in enumerate(freq_entries):
        row = rows[index] if index < len(rows) else None
        channel = row_to_channel.get(id(row)) if row is not None else None
        if channel is None:
            continue
        mhz = getattr(channel, "wireless_frequency_mhz", None)
        khz = int(round(mhz * 1000)) if mhz is not None else 0
        _set_text(entry, "value", str(khz))
        gr_ch, _group_channel = _gr_ch_markup(
            getattr(channel, "wireless_group", None),
            getattr(channel, "wireless_channel", None),
        )
        _set_text(entry, "gr_ch", gr_ch)
        _set_text(entry, "source_name", _channel_display_name(channel))

    return '<?xml version="1.0" encoding="UTF-8"?>\n' + ET.tostring(root, encoding="unicode")


# A real, minimal Wireless Workbench show file (reduced from a Shure export). WWB show
# files have a large, version-specific structure that cannot be hand-authored, so for
# "export without an upload" we clone this validated template and write Stagewire's
# channels into it — the same mechanism as round-tripping an uploaded file.
_TEMPLATE_PATH = Path(__file__).resolve().parent / "templates" / "wwb_template.shw"


def _expand_template_to(template_xml: str, count: int) -> str:
    """Clone a WWB template's single device/channel/coordination entry up to ``count``.

    The bundled template ships with one channel; a from-scratch export needs one per
    Stagewire wireless channel. Cloning the real (WWB-valid) structure is what keeps the
    emitted file openable in WWB, since the schema cannot be reproduced from scratch.
    """
    if count <= 0:
        return template_xml
    root = ET.fromstring(template_xml)
    device = root.find(".//inventory/device")
    if device is None:
        return template_xml
    device_id = (device.findtext("id") or "").strip()

    channels = device.findall("channel")
    if channels:
        proto = channels[0]
        for _ in range(len(channels), count):
            device.append(copy.deepcopy(proto))
        for extra in device.findall("channel")[count:]:
            device.remove(extra)
        for i, ch in enumerate(device.findall("channel")):
            ch.set("number", str(i + 1))

    mc = root.find(".//coordinated_data_root/mic_channels")
    if mc is not None:
        fes = mc.findall("freq_entry")
        if fes:
            proto_fe = fes[0]
            for _ in range(len(fes), count):
                mc.append(copy.deepcopy(proto_fe))
            for extra in mc.findall("freq_entry")[count:]:
                mc.remove(extra)
            fes = mc.findall("freq_entry")
            for i, fe in enumerate(fes):
                fe.set("id", f"{device_id}-{i}")
                sid = fe.find("source_id")
                if sid is not None:
                    sid.text = f"{device_id}-{i}"
            mc.set("count", str(len(fes)))

    cm = root.find(".//coordination_info/channel_management")
    if cm is not None:
        chans_el = cm.find("channels")
        if chans_el is not None:
            ids = chans_el.findall("id")
            if ids:
                proto_id = ids[0]
                for _ in range(len(ids), count):
                    chans_el.append(copy.deepcopy(proto_id))
                for extra in chans_el.findall("id")[count:]:
                    chans_el.remove(extra)
                ids = chans_el.findall("id")
                for i, id_el in enumerate(ids):
                    id_el.text = f"{device_id}-{i}"
                    id_el.set("coordination_include", "true")
                    id_el.set("active_channel", "true")

    return ET.tostring(root, encoding="unicode")


def build_show_file_from_scratch(channels: list) -> str:
    """Generate a WWB ``.shw`` from Stagewire channels when no file was uploaded.

    Clones the bundled template (expanded to the number of wireless channels) and writes
    Stagewire's frequencies/names into it, so the result opens in Wireless Workbench.
    """
    template = _TEMPLATE_PATH.read_text(encoding="utf-8")
    wireless = [c for c in channels if getattr(c, "input_type", None) == "wireless"]
    expanded = _expand_template_to(template, len(wireless))
    return apply_stagewire_to_show_file(expanded, channels)
