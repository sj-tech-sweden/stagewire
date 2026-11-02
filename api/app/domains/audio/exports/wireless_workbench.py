import xml.etree.ElementTree as ET
from datetime import datetime
from xml.etree.ElementTree import Element, SubElement

from .base import ConsoleExporter, ExportResult


def _gr_ch_strings(group: str | None, channel: str | None) -> tuple[str, str]:
    """Render WWB group/channel markers, using the unset form when not coordinated."""
    if group and channel:
        return f"G:{group} Ch:{channel}", f"{group},{channel}"
    return "G:-- Ch:--", "--,--"


class WirelessWorkbenchExporter(ConsoleExporter):
    """A Wireless Workbench ``.shw`` show file of the list's wireless channels.

    The coordinated channels carry the frequency (in kHz), group/channel and name so
    the file can be opened back in WWB or re-imported into Stagewire. Only channels
    with ``input_type == 'wireless'`` are included.
    """

    key = "wireless_workbench"
    label = "Wireless Workbench (.shw)"
    description = (
        "A Wireless Workbench show file (.shw) with the wireless channels' coordinated "
        "frequencies, group and channel."
    )
    media_type = "application/xml"
    file_extension = ".shw"

    def export(self, channel_list, channels, outputs) -> ExportResult:
        wireless = [c for c in channels if getattr(c, "input_type", None) == "wireless"]
        wireless = sorted(wireless, key=lambda c: c.channel_number or 0)

        now = datetime.now()
        show = Element(
            "show",
            {
                "date": now.strftime("%a %b %d %Y"),
                "source": "Stagewire",
                "version": "1.0",
                "time": now.strftime("%H:%M:%S"),
                "appl_version": "Stagewire",
            },
        )
        props = SubElement(show, "show_properties", {"version": "1.0"})
        info = SubElement(props, "show_info")
        SubElement(info, "name").text = channel_list.name or "Channel list"

        inv = SubElement(show, "inventory", {"version": "2.1"})
        zones = SubElement(inv, "zones", {"version": "1.1"})
        SubElement(zones, "zone", {"color": "#7863ed", "ordinal": "0"}).text = "Default"

        coord = SubElement(show, "coordination_info")
        cm = SubElement(coord, "channel_management")
        chans = SubElement(cm, "channels")
        acl = SubElement(chans, "active_channel_list")

        for index, channel in enumerate(wireless, start=1):
            mhz = channel.wireless_frequency_mhz
            khz = int(round(mhz * 1000)) if mhz is not None else 0
            gr_ch, group_channel = _gr_ch_strings(channel.wireless_group, channel.wireless_channel)
            name = (
                channel.source_label
                or channel.wireless_pack
                or f"Channel {channel.channel_number or index}"
            )
            ch = SubElement(acl, "channel")
            SubElement(ch, "id").text = f"stagewire-{index}"
            SubElement(ch, "channel_name").text = name
            SubElement(ch, "gr_ch").text = gr_ch
            SubElement(ch, "group_channel").text = group_channel
            SubElement(ch, "frequency", {"type": "3"}).text = str(khz)
            SubElement(ch, "color").text = "5789784"

        xml_str = ET.tostring(show, encoding="unicode")
        xml_bytes = ('<?xml version="1.0" encoding="UTF-8"?>\n' + xml_str).encode("utf-8")
        name = (channel_list.name or "channel-list").replace(" ", "_")
        return ExportResult(
            content=xml_bytes,
            filename=f"{name}_wireless.shw",
            media_type=self.media_type,
        )
