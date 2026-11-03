import xml.etree.ElementTree as ET

from app.domains.audio import wwb

from .base import ConsoleExporter, ExportResult


class WirelessWorkbenchExporter(ConsoleExporter):
    """A Wireless Workbench ``.shw`` show file of the list's wireless channels.

    When the list has previously imported a ``.shw`` (attached to the channel list node
    as ``wwb_show_file_content`` by the caller), that file is re-emitted with Stagewire's
    coordinated frequencies written back into it, so it round-trips through WWB. Otherwise
    a ``.shw`` is generated from the channels by cloning the bundled WWB template and
    writing Stagewire's data into it (WWB show files cannot be hand-authored from scratch).
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
        template = getattr(channel_list, "wwb_show_file_content", None)
        if template:
            try:
                content = wwb.apply_stagewire_to_show_file(template, channels).encode("utf-8")
                name = (channel_list.name or "channel-list").replace(" ", "_")
                return ExportResult(
                    content=content,
                    filename=f"{name}_wireless.shw",
                    media_type=self.media_type,
                )
            except ET.ParseError:
                # fall through to a generated file if the stored template is corrupt
                pass

        content = wwb.build_show_file_from_scratch(channels).encode("utf-8")
        name = (channel_list.name or "channel-list").replace(" ", "_")
        return ExportResult(
            content=content,
            filename=f"{name}_wireless.shw",
            media_type=self.media_type,
        )
