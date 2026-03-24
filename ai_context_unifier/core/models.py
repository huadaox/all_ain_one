from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime
from abc import ABC, abstractmethod


@dataclass
class Message:
    role: str  # "user" | "assistant" | "tool"
    content: str
    timestamp: datetime | None = None
    tool_name: str | None = None


@dataclass
class Conversation:
    id: str
    tool: str  # "claude-code" | "cursor" | ...
    project: str = ""
    messages: list[Message] = field(default_factory=list)
    started_at: datetime | None = None
    title: str = ""

    def auto_title(self) -> str:
        if self.title:
            return self.title
        for msg in self.messages:
            if msg.role == "user" and msg.content.strip():
                text = msg.content.strip()
                # Strip XML tags
                if "<" in text:
                    import re

                    text = re.sub(r"<[^>]+>", "", text).strip()
                first_line = text.split("\n")[0][:80]
                return first_line if first_line else "Untitled"
        return "Untitled"


class BaseExtractor(ABC):
    @abstractmethod
    def extract(self) -> list[Conversation]:
        """Extract all conversations."""

    def extract_since(self, since: datetime) -> list[Conversation]:
        """Extract conversations since a given time."""
        normalized_since = _normalize_datetime(since)
        return [
            c
            for c in self.extract()
            if c.started_at and _normalize_datetime(c.started_at) >= normalized_since
        ]


def _normalize_datetime(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=UTC)
    return value.astimezone(UTC)
