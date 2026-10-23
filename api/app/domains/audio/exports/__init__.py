from .allen_heath_cq import AllenHeathCqExporter
from .allen_heath_gld import AllenHeathGldExporter
from .allen_heath_qu import AllenHeathQuExporter
from .base import ConsoleExporter
from .generic_csv import GenericCsvExporter
from .generic_xlsx import GenericXlsxExporter

EXPORTERS: list[ConsoleExporter] = [
    GenericCsvExporter(),
    GenericXlsxExporter(),
    AllenHeathQuExporter(),
    AllenHeathCqExporter(),
    AllenHeathGldExporter(),
]

_EXPORTER_MAP = {e.key: e for e in EXPORTERS}


def list_exporters() -> list[ConsoleExporter]:
    return EXPORTERS


def get_exporter(key: str) -> ConsoleExporter | None:
    return _EXPORTER_MAP.get(key)
