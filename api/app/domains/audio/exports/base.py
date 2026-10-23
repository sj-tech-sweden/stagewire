from abc import ABC, abstractmethod
from dataclasses import dataclass


@dataclass
class ExportResult:
    content: bytes
    filename: str
    media_type: str


class ConsoleExporter(ABC):
    key: str = ""
    label: str = ""
    description: str = ""
    media_type: str = "application/octet-stream"
    file_extension: str = ".bin"

    @abstractmethod
    def export(self, channel_list, channels, outputs) -> ExportResult:
        raise NotImplementedError
