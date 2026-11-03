"""Reduce a real Wireless Workbench .shw to a minimal-but-valid template.

WWB show files have a large, version-specific structure (typed device channels,
coordination info with scan/TV-avoidance data, coordinated_data_root freq entries)
that cannot be hand-authored reliably. To let Stagewire *generate* a .shw from
scratch (without the user uploading one first), we keep one real device/channel as
a skeleton and let the exporter mutate its frequencies/names with Stagewire data.

Run from the api/ dir:  python scripts/make_wwb_template.py \
    "/path/to/real.shw"  > app/domains/audio/templates/wwb_template.shw
"""

import sys
import xml.etree.ElementTree as ET

NS_KEEP = False  # WWB files are non-namespaced; preserve attribute order best-effort.


def main() -> int:
    if len(sys.argv) < 2:
        print("usage: make_wwb_template.py <real.shw> [out.shw]", file=sys.stderr)
        return 2
    src = sys.argv[1]
    tree = ET.parse(src)
    root = tree.getroot()

    # Mark the whole thing as a Stagewire-generated base template.
    root.set("source", "Stagewire")

    # --- inventory: keep only the first device and its first channel ---
    inventory = root.find("inventory")
    if inventory is not None:
        devices = inventory.findall("device")
        for dev in devices[1:]:
            inventory.remove(dev)
        if devices:
            dev = devices[0]
            device_id = dev.findtext("id")
            channels = dev.findall("channel")
            for ch in channels[1:]:
                dev.remove(ch)
            if channels:
                ch = channels[0]
                ch.set("number", "1")
                name = ch.find("channel_name")
                if name is not None:
                    name.text = "Channel 1"
                freq = ch.find("frequency")
                if freq is not None:
                    freq.text = "558000"
                for tag in ("gr_ch", "group_channel"):
                    el = ch.find(tag)
                    if el is not None:
                        el.text = "--,--" if tag == "group_channel" else "G:-- Ch:--"

    # --- coordination_info: keep a single active channel id, trim TV avoidance ---
    ci = root.find("coordination_info")
    if ci is not None:
        cm = ci.find("channel_management")
        if cm is not None:
            chans = cm.find("channels")
            if chans is not None:
                ids = chans.findall("id")
                for i in ids[1:]:
                    chans.remove(i)
        ce = ci.find("channel_exclusions")
        if ce is not None:
            tv = ce.find("channel_avoidance_info")
            if tv is not None:
                chs = tv.findall("channel")
                for c in chs[5:]:
                    tv.remove(c)
            # Drop per-channel exclusion lists (legacy_weighted etc.) to keep it small.
            for child in list(ce):
                if child.tag not in ("location_info", "channel_avoidance_info"):
                    ce.remove(child)

    # --- coordinated_data_root: keep only the first freq_entry ---
    cdr = root.find("coordinated_data_root")
    if cdr is not None:
        # mic_channels/freq_entry if present
        mc = cdr.find("mic_channels")
        if mc is not None:
            acl = mc.find("active_channel_list")
            if acl is not None:
                for fe in acl.findall("freq_entry")[1:]:
                    acl.remove(fe)
        for fe in cdr.findall("freq_entry")[1:]:
            cdr.remove(fe)

    ET.indent(root, space="    ")
    out = sys.argv[2] if len(sys.argv) > 2 else None
    xml_bytes = (
        '<?xml version="1.0" encoding="UTF-8"?>\n'
        + ET.tostring(root, encoding="unicode")
    )
    if out:
        with open(out, "w", encoding="utf-8") as fh:
            fh.write(xml_bytes)
    else:
        sys.stdout.write(xml_bytes)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
