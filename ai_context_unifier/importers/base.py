from __future__ import annotations

from abc import ABC, abstractmethod
from pathlib import Path

from ..core.models import Conversation


class BaseImporter(ABC):
    @abstractmethod
    def import_path(self, path: Path) -> list[Conversation]:
        raise NotImplementedError
