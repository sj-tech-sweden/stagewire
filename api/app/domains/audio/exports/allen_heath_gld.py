from .base import ConsoleExporter, ExportResult
from .common import build_patch_zip

_GLD_README = """Stagewire - Allen & Heath GLD scene export (experimental)
========================================================

This ZIP contains a console-agnostic patch sheet (patch.csv) only.

The GLD scene-file format is not publicly documented, so Stagewire cannot yet
generate a loadable GLD .DAT scene. To move the names onto the console:

1. Open patch.csv and copy the input channel names into the GLD mixer (or the
   GLD OneMix / offline editor).
2. Alternatively, use the Allen & Heath mixing-station / offline tools as an
   intermediate step to build the show file from this sheet.

GLD channel names are limited to 6 characters.
"""


class AllenHeathGldExporter(ConsoleExporter):
    key = "allen_heath_gld"
    label = "Allen & Heath GLD (sheet, experimental)"
    description = (
        "GLD scene format is undocumented, so this returns a readable patch "
        "sheet for manual entry rather than a loadable scene."
    )
    media_type = "application/zip"
    file_extension = ".zip"

    def export(self, channel_list, channels, outputs) -> ExportResult:
        content = build_patch_zip(channel_list, channels, outputs, _GLD_README)
        return ExportResult(
            content=content,
            filename=f"{channel_list.name}-GLD.zip".replace(" ", "_"),
            media_type=self.media_type,
        )
