"""Helpers for associating wireless channels with Shure Wireless Workbench.

Wireless Workbench (WWB) coordinates RF and can export a frequency list as CSV.
We support two directions:

- **Export**: the ``wireless_workbench`` console exporter turns the job's wireless
  channels (those with ``input_type == 'wireless'``) into a WWB-style CSV
  (pack, frequency in MHz, group, channel) that can be opened back in WWB.
- **Import**: a WWB frequency-list CSV is parsed here and matched to the job's
  existing wireless channels by pack label (or channel number + source) so the
  coordinated frequencies land on the right channels.

Frequencies are stored as structured fields on the channel (``wireless_frequency_mhz``,
``wireless_group``, ``wireless_channel``); the historical free-text ``wireless_frequency``
string is parsed on read for backwards compatibility and removed by a migration.
"""

import csv
import io
import re

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


# Header aliases -> normalised field. Order matters: a header is bound to the first
# matching set, so more specific names come before generic ones.
_HEADER_MAP = [
    ("wireless_pack", {"wireless_pack", "pack", "bodypack", "beltpack", "receiver", "rx"}),
    ("source_label", {"source_label", "source", "label", "performer", "device"}),
    (
        "wireless_frequency_mhz",
        {"wireless_frequency_mhz", "frequency", "freq", "frequency_mhz", "tx_frequency", "tx_freq"},
    ),
    ("wireless_group", {"wireless_group", "group", "freq_group", "tv_group"}),
]

# "Channel" on its own is ambiguous: WWB uses it for the Shure channel number when a
# "Group" column is present, otherwise it means our channel number. Resolved per-file.
_CHANNEL_NUMBER_HEADERS = {"channel_number", "ch", "input", "input_channel", "input_number"}


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


def _canonical_header(header: str, has_group: bool) -> str | None:
    key = re.sub(r"[^a-z0-9]", "", header.strip().lower())
    for field, aliases in _HEADER_MAP:
        if key in aliases:
            return field
    if key in _CHANNEL_NUMBER_HEADERS:
        return "channel_number"
    # bare "channel" is the Shure channel when a group exists, else our channel number
    if key == "channel":
        return "wireless_channel" if has_group else "channel_number"
    return None


def parse_wwb_frequency_csv(text: str) -> list[dict]:
    """Parse a WWB-style frequency-list CSV into normalised wireless rows.

    Each returned dict has some of: ``channel_number``, ``source_label``,
    ``wireless_pack``, ``wireless_frequency_mhz``, ``wireless_group``,
    ``wireless_channel`` (only the columns present in the file are included). Rows
    without a frequency and without a pack/source are skipped.
    """
    reader = csv.DictReader(io.StringIO(text))
    headers = reader.fieldnames or []
    group_headers = {"wireless_group", "group", "freq_group", "tv_group"}
    has_group = any(re.sub(r"[^a-z0-9]", "", h.strip().lower()) in group_headers for h in headers)
    columns = {}
    for index, header in enumerate(headers):
        field = _canonical_header(header, has_group)
        if field:
            columns[index] = field

    rows: list[dict] = []
    for raw in reader:
        values = list(raw.values())
        row: dict = {}
        for index, field in columns.items():
            cell = (values[index] or "").strip()
            if not cell:
                continue
            if field == "channel_number":
                as_int = _to_float(cell)
                row[field] = int(as_int) if as_int is not None else None
            elif field == "wireless_frequency_mhz":
                row[field] = parse_mhz(cell)
            else:
                row[field] = cell
        if row:
            rows.append(row)
    return rows


def match_wireless_rows(channels: list, rows: list[dict]) -> tuple[list[tuple], list[dict]]:
    """Match parsed WWB rows to existing wireless channels.

    Returns ``(matched, unmatched)`` where ``matched`` is a list of
    ``(channel, row)`` for channels whose ``input_type == 'wireless'`` and whose
    pack label (or channel number + source label) matches a row. ``unmatched`` is the
    list of rows that did not match any channel.
    """
    by_pack: dict[str, list] = {}
    by_number_source: dict[tuple, list] = {}
    for channel in channels:
        if getattr(channel, "input_type", None) != "wireless":
            continue
        pack = (getattr(channel, "wireless_pack", None) or "").strip().lower()
        if pack:
            by_pack.setdefault(pack, []).append(channel)
        number = getattr(channel, "channel_number", None)
        source = (getattr(channel, "source_label", None) or "").strip().lower()
        if number is not None:
            by_number_source.setdefault((number, source), []).append(channel)

    matched: list[tuple] = []
    seen_channel_ids = set()
    unmatched: list[dict] = []
    for row in rows:
        row_pack = (row.get("wireless_pack") or "").strip().lower()
        row_number = row.get("channel_number")
        row_source = (row.get("source_label") or "").strip().lower()
        candidates = by_pack.get(row_pack, []) if row_pack else []
        if not candidates and row_number is not None:
            candidates = by_number_source.get((row_number, row_source), [])
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
