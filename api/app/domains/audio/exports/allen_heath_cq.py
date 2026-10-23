from .base import ConsoleExporter, ExportResult
from .common import build_patch_zip

_CQ_README = """Stagewire - Allen & Heath CQ patch sheet (experimental)
======================================================

The CQ series has no documented scene-file import, so this ZIP contains a
console-agnostic patch sheet (patch.csv) that you can print or copy into the
mixer's channel setup.

QU/CQ channel names are limited to 6 characters.
"""


class AllenHeathCqExporter(ConsoleExporter):
    key = "allen_heath_cq"
    label = "Allen & Heath CQ (sheet, experimental)"
    description = (
        "CQ consoles have no documented scene import, so this returns a "
        "readable patch sheet for manual entry."
    )
    media_type = "application/zip"
    file_extension = ".zip"

    def export(self, channel_list, channels, outputs) -> ExportResult:
        content = build_patch_zip(channel_list, channels, outputs, _CQ_README)
        return ExportResult(
            content=content,
            filename=f"{channel_list.name}-CQ.zip".replace(" ", "_"),
            media_type=self.media_type,
        )
