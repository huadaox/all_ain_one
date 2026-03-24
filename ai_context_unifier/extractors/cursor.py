from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path

from ..core.models import BaseExtractor, Conversation, Message


class CursorExtractor(BaseExtractor):
    """Extract conversations from Cursor IDE agent transcripts."""

    def __init__(self, base_dir: Path | None = None):
        self.base_dir = base_dir or Path.home() / ".cursor"
        self.projects_dir = self.base_dir / "projects"

    def extract(self) -> list[Conversation]:
        if not self.projects_dir.exists():
            return []

        conversations = []
        for project_dir in sorted(self.projects_dir.iterdir()):
            if not project_dir.is_dir():
                continue
            transcripts_dir = project_dir / "agent-transcripts"
            if not transcripts_dir.exists():
                continue

            project_name = self._decode_project_name(project_dir.name)

            for session_dir in sorted(transcripts_dir.iterdir()):
                if not session_dir.is_dir():
                    continue
                for jsonl_file in session_dir.glob("*.jsonl"):
                    conv = self._parse_transcript(
                        jsonl_file, project_name, session_dir.name
                    )
                    if conv and conv.messages:
                        conversations.append(conv)

        return conversations

    def _parse_transcript(
        self, path: Path, project_name: str, session_id: str
    ) -> Conversation | None:
        messages: list[Message] = []

        for line in path.read_text(encoding="utf-8").splitlines():
            if not line.strip():
                continue
            try:
                entry = json.loads(line)
            except json.JSONDecodeError:
                continue

            role = entry.get("role", "")
            message_data = entry.get("message", {})
            content_parts = message_data.get("content", [])

            text_parts = []
            for part in content_parts:
                if isinstance(part, dict) and part.get("type") == "text":
                    text_parts.append(part.get("text", ""))

            content = "\n".join(text_parts)
            if not content.strip():
                continue

            messages.append(
                Message(
                    role=role if role in ("user", "assistant") else "assistant",
                    content=content,
                    timestamp=None,  # Cursor transcripts don't have timestamps per message
                )
            )

        if not messages:
            return None

        # Use file modification time as session time
        started_at = datetime.fromtimestamp(path.stat().st_mtime, tz=UTC)

        conv = Conversation(
            id=session_id,
            tool="cursor",
            project=project_name,
            messages=messages,
            started_at=started_at,
        )
        conv.title = conv.auto_title()
        return conv

    @staticmethod
    def _decode_project_name(encoded: str) -> str:
        """Decode Cursor's project directory name back to a path."""
        # e.g. "mnt-e-Code-claude-narrative-flywheel" -> "/mnt/e/Code/claude/narrative-flywheel"
        return "/" + encoded.replace("-", "/")
