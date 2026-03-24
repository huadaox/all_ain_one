from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path

from ..core.models import BaseExtractor, Conversation, Message


OPENCODE_MARKERS = (
    "<!-- omo_internal_initiator -->",
    "[system directive: oh-my-opencode",
    "sisyphus (ultraworker)",
    "sisyphus-junior",
    "/.cache/opencode",
    "/.local/share/opencode",
    "ultrawork mode enabled!",
)


class ClaudeTranscriptExtractor(BaseExtractor):
    tool_name = "claude-code"

    def __init__(self, base_dir: Path | None = None):
        self.base_dir = base_dir or Path.home() / ".claude"
        self.transcripts_dir = self.base_dir / "transcripts"
        # history.jsonl maps sessionId -> project
        self._session_projects: dict[str, str] = {}
        self._load_history()

    def _load_history(self):
        history_file = self.base_dir / "history.jsonl"
        if not history_file.exists():
            return
        for line in history_file.read_text(encoding="utf-8").splitlines():
            if not line.strip():
                continue
            try:
                entry = json.loads(line)
                sid = entry.get("sessionId", "")
                project = entry.get("project", "")
                if sid and project:
                    self._session_projects[sid] = project
            except json.JSONDecodeError:
                continue

    def extract(self) -> list[Conversation]:
        if not self.transcripts_dir.exists():
            return []

        conversations = []
        for f in sorted(self.transcripts_dir.glob("ses_*.jsonl")):
            conv = self._parse_transcript(f)
            if conv and conv.messages:
                conversations.append(conv)
        return conversations

    def _parse_transcript(self, path: Path) -> Conversation | None:
        # Session ID from filename: ses_<id>.jsonl
        session_id = path.stem.removeprefix("ses_")
        project = self._session_projects.get(session_id, "")

        entries = self._load_entries(path)
        if not entries or not self._should_include_entries(entries):
            return None

        messages: list[Message] = []
        for entry in entries:
            msg_type = entry.get("type", "")
            timestamp = self._parse_ts(entry.get("timestamp"))
            content = ""

            if msg_type == "user":
                content = self._extract_content(entry.get("content", ""))
                if content:
                    messages.append(
                        Message(role="user", content=content, timestamp=timestamp)
                    )

            elif msg_type == "assistant":
                content = self._extract_content(entry.get("content", ""))
                if content:
                    messages.append(
                        Message(role="assistant", content=content, timestamp=timestamp)
                    )

            elif msg_type == "tool_use":
                tool_name = entry.get("tool_name", "unknown")
                tool_input = entry.get("tool_input", {})
                input_str = (
                    json.dumps(tool_input, ensure_ascii=False, indent=2)
                    if isinstance(tool_input, dict)
                    else str(tool_input)
                )
                messages.append(
                    Message(
                        role="tool",
                        content=f"[Tool Call: {tool_name}]\n{input_str}",
                        timestamp=timestamp,
                        tool_name=tool_name,
                    )
                )

            elif msg_type == "tool_result":
                tool_name = entry.get("tool_name", "unknown")
                output = entry.get("tool_output", {})
                output_text = (
                    output.get("output", "")
                    if isinstance(output, dict)
                    else str(output)
                )
                # Truncate long tool outputs
                if len(output_text) > 500:
                    output_text = output_text[:500] + "\n... (truncated)"
                messages.append(
                    Message(
                        role="tool",
                        content=f"[Tool Result: {tool_name}]\n{output_text}",
                        timestamp=timestamp,
                        tool_name=tool_name,
                    )
                )

        if not messages:
            return None

        started_at = messages[0].timestamp
        conv = Conversation(
            id=session_id,
            tool=self.tool_name,
            project=project,
            messages=messages,
            started_at=started_at,
        )
        conv.title = conv.auto_title()
        return conv

    @staticmethod
    def _load_entries(path: Path) -> list[dict]:
        entries: list[dict] = []
        for line in path.read_text(encoding="utf-8").splitlines():
            if not line.strip():
                continue
            try:
                entry = json.loads(line)
            except json.JSONDecodeError:
                continue
            if isinstance(entry, dict):
                entries.append(entry)
        return entries

    def _should_include_entries(self, entries: list[dict]) -> bool:
        return True

    @classmethod
    def _is_opencode_transcript(cls, entries: list[dict]) -> bool:
        for entry in entries:
            payload = json.dumps(entry, ensure_ascii=False).lower()
            if any(marker in payload for marker in OPENCODE_MARKERS):
                return True
        return False

    @staticmethod
    def _extract_content(content) -> str:
        if isinstance(content, str):
            return content
        if isinstance(content, list):
            parts = []
            for item in content:
                if isinstance(item, dict) and item.get("type") == "text":
                    parts.append(item.get("text", ""))
            return "\n".join(parts)
        return str(content) if content else ""

    @staticmethod
    def _parse_ts(ts) -> datetime | None:
        if not ts:
            return None
        if isinstance(ts, (int, float)):
            return datetime.fromtimestamp(ts / 1000)
        if isinstance(ts, str):
            try:
                return datetime.fromisoformat(ts.replace("Z", "+00:00"))
            except ValueError:
                return None
        return None


class ClaudeCodeExtractor(ClaudeTranscriptExtractor):
    tool_name = "claude-code"

    def _should_include_entries(self, entries: list[dict]) -> bool:
        return not self._is_opencode_transcript(entries)


class OpenCodeExtractor(ClaudeTranscriptExtractor):
    tool_name = "opencode"

    def _should_include_entries(self, entries: list[dict]) -> bool:
        return self._is_opencode_transcript(entries)
