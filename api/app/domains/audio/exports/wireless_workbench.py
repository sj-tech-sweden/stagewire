import csv
import io

from .base import ConsoleExporter, ExportResult


class WirelessWorkbenchExporter(ConsoleExporter):
    """A WWB-style CSV of the list's wireless channels (frequency, group, channel).

    Shure Wireless Workbench can import a frequency list CSV; this gives the
    coordinated frequencies back to WWB after they have been entered in Stagewire.
    Only channels with ``input_type == 'wireless'`` are included.
    """

    key = "wireless_workbench"
    label = "Wireless Workbench (CSV)"
    description = (
        "A frequency list of the wireless channels (pack, frequency in MHz, group, "
        "channel) that Wireless Workbench can import."
    )
    media_type = "text/csv"
    file_extension = ".csv"

    HEADER = ["Channel", "Source", "Pack", "Frequency (MHz)", "Group", "Channel"]

    def export(self, channel_list, channels, outputs) -> ExportResult:
        wireless = [c for c in channels if getattr(c, "input_type", None) == "wireless"]
        buf = io.StringIO()
        writer = csv.writer(buf)
        writer.writerow(self.HEADER)
        for channel in sorted(wireless, key=lambda c: c.channel_number or 0):
            writer.writerow(
                [
                    channel.channel_number or "",
                    channel.source_label or "",
                    channel.wireless_pack or "",
                    channel.wireless_frequency_mhz
                    if channel.wireless_frequency_mhz is not None
                    else "",
                    channel.wireless_group or "",
                    channel.wireless_channel or "",
                ]
            )
        name = (channel_list.name or "channel-list").replace(" ", "_")
        return ExportResult(
            content=buf.getvalue().encode("utf-8"),
            filename=f"{name}_wireless.csv",
            media_type=self.media_type,
        )
