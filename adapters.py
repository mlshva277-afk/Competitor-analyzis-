"""Explicit adapter boundary: network collectors never pretend to have fetched data."""
from abc import ABC, abstractmethod
from dataclasses import dataclass
from ingest import import_frame, read_table, log_run, PLATFORMS


@dataclass
class SyncResult:
    status: str
    rows: int = 0
    message: str = ''


class SourceAdapter(ABC):
    @abstractmethod
    def sync(self, factory) -> SyncResult:
        pass


class FileAdapter(SourceAdapter):
    def __init__(self, content, filename, kind, dataset='real'):
        self.content, self.filename, self.kind, self.dataset = content, filename, kind, dataset

    def sync(self, factory):
        try:
            frame = read_table(self.content, self.filename)
        except Exception as exc:
            log_run(factory, self.filename, 'import', 'error', 0, str(exc))
            raise
        count = import_frame(factory, frame, self.kind, self.filename, self.dataset)
        return SyncResult('success', count, 'Импорт завершён; только загруженная выборка')


class StubAdapter(SourceAdapter):
    def __init__(self, platform):
        if platform not in PLATFORMS:
            raise ValueError('Неизвестная платформа')
        self.platform = platform

    def sync(self, factory):
        message = 'Сетевой адаптер не реализован. Используйте CSV/XLSX; доступ и условия API не проверены.'
        log_run(factory, 'stub:' + self.platform, self.platform, 'not_configured', 0, message)
        return SyncResult('not_configured', message=message)
