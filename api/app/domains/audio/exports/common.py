import csv
import io
import zipfile

INPUT_HEADER = [
    "channel_number",
    "source_label",
    "input_type",
    "device",
    "transducer",
    "stand_type",
    "connector",
    "phantom_power",
    "stereo",
    "notes",
]

OUTPUT_HEADER = [
    "output_number",
    "name",
    "mode",
    "connector",
    "notes",
]


def safe_filename(name: str) -> str:
    clean = "".join(c if c.isalnum() or c in (" ", "-", "_") else "_" for c in name).strip()
    return clean or "channel-list"


def channel_row(c) -> list:
    return [
        c.channel_number or "",
        c.source_label or "",
        c.input_type or "",
        c.device or "",
        c.transducer or "",
        c.stand_type or "",
        c.connector or "",
        c.phantom_power or "",
        c.stereo or "",
        c.notes or "",
    ]


def output_row(o) -> list:
    return [
        o.position if o.position is not None else "",
        o.name or "",
        o.mode or "",
        o.connector or "",
        o.notes or "",
    ]


def render_csv(channel_list, channels, outputs) -> bytes:
    buf = io.StringIO()
    writer = csv.writer(buf)
    writer.writerow(["Stagewire channel list export"])
    writer.writerow([f"Name: {channel_list.name}"])
    writer.writerow([f"Console: {channel_list.mixer_product_name or 'unspecified'}"])
    writer.writerow([])
    writer.writerow(INPUT_HEADER)
    for c in sorted(channels, key=lambda x: x.channel_number or 0):
        writer.writerow(channel_row(c))
    writer.writerow([])
    writer.writerow(OUTPUT_HEADER)
    for o in sorted(outputs, key=lambda x: x.position or 0):
        writer.writerow(output_row(o))
    return buf.getvalue().encode("utf-8")


def render_inputs_csv(channel_list, channels) -> bytes:
    buf = io.StringIO()
    writer = csv.writer(buf)
    writer.writerow(INPUT_HEADER)
    for c in sorted(channels, key=lambda x: x.channel_number or 0):
        writer.writerow(channel_row(c))
    return buf.getvalue().encode("utf-8")


def render_outputs_csv(channel_list, outputs) -> bytes:
    buf = io.StringIO()
    writer = csv.writer(buf)
    writer.writerow(OUTPUT_HEADER)
    for o in sorted(outputs, key=lambda x: x.position or 0):
        writer.writerow(output_row(o))
    return buf.getvalue().encode("utf-8")


def build_patch_zip(channel_list, channels, outputs, readme: str) -> bytes:
    csv_bytes = render_csv(channel_list, channels, outputs)
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
        zf.writestr(f"{safe_filename(channel_list.name)}.csv", csv_bytes)
        zf.writestr("README.txt", readme)
    return buf.getvalue()
