import io
import zipfile

from .base import ConsoleExporter, ExportResult
from .common import (
    render_inputs_csv,
    render_outputs_csv,
    safe_filename,
)


class GenericCsvExporter(ConsoleExporter):
    key = "generic_csv"
    label = "Generic CSV (inputs + outputs, .zip)"
    description = (
        "Two separate CSV files (inputs.csv, outputs.csv) for the channel "
        "list, bundled in a ZIP so each is a valid single-table CSV."
    )
    media_type = "application/zip"
    file_extension = ".zip"

    def export(self, channel_list, channels, outputs) -> ExportResult:
        buf = io.BytesIO()
        with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
            base = safe_filename(channel_list.name)
            zf.writestr(f"{base}_inputs.csv", render_inputs_csv(channel_list, channels))
            zf.writestr(
                f"{base}_outputs.csv", render_outputs_csv(channel_list, outputs)
            )
        return ExportResult(
            content=buf.getvalue(),
            filename=f"{base}_csv.zip",
            media_type=self.media_type,
        )
