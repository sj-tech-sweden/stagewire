import os

from .base import ConsoleExporter, ExportResult
from .common import build_patch_zip, safe_filename
from .qu_scene import QU_MAX_INPUTS, patch_qu_scene

_QU_BASE_SCENE_PATH = os.environ.get("QU_BASE_SCENE_PATH", "")

_QU_README = """Stagewire - Allen & Heath QU scene export (experimental)
==========================================================

This ZIP contains a console-agnostic patch sheet (patch.csv) because a
ready-to-load QU .DAT scene could not be generated automatically.

Why?
----
The public QU scene-file format is only partially documented (the reverse
engineering is work-in-progress, with several undecoded sections). Building a
valid .DAT from scratch is therefore unreliable, and the scene file itself is
the vendor's/author's sample data, so it is not bundled with Stagewire.

How to get a loadable QU scene
------------------------------
Option A (automatic): place a base QU scene exported from YOUR OWN mixer (or the
Qu-24 Offline Editor) at the path configured by the QU_BASE_SCENE_PATH
environment variable. Stagewire will then patch the first 32 input channel names
into that scene and recompute the QU checksum, producing a loadable .DAT.

Option B (manual): open patch.csv in the Qu-24 Offline Editor
(https://github.com/BryceYoung/qu-24-Offline-Editor) or on the mixer and copy the
channel names across.

Note: QU channel names are limited to 6 characters.
"""


class AllenHeathQuExporter(ConsoleExporter):
    key = "allen_heath_qu"
    label = "Allen & Heath QU Scene (.DAT, experimental)"
    description = (
        "Patches input channel names into a QU show scene and recomputes the "
        "QU checksum when a base scene is configured; otherwise returns a "
        "readable patch sheet plus instructions."
    )
    media_type = "application/octet-stream"
    file_extension = ".dat"

    def export(self, channel_list, channels, outputs) -> ExportResult:
        if _QU_BASE_SCENE_PATH and os.path.exists(_QU_BASE_SCENE_PATH):
            names = [
                c.source_label or "" for c in sorted(channels, key=lambda x: x.channel_number or 0)
            ][:QU_MAX_INPUTS]
            with open(_QU_BASE_SCENE_PATH, "rb") as fh:
                data = patch_qu_scene(fh.read(), names)
            return ExportResult(
                content=data,
                filename=f"{safe_filename(channel_list.name)}.dat",
                media_type=self.media_type,
            )
        content = build_patch_zip(channel_list, channels, outputs, _QU_README)
        return ExportResult(
            content=content,
            filename=f"{safe_filename(channel_list.name)}-QU.zip",
            media_type="application/zip",
        )
