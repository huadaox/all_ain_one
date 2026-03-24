from __future__ import annotations

import hashlib
import json
from datetime import UTC, datetime
from pathlib import Path
from zipfile import ZipFile

from ..core.models import Conversation, Message
from .base import BaseImporter


class ChatGPTImporter(BaseImporter):
    def import_path(self, path: Path) -> list[Conversation]:
        raw = self._load_export(path)
        payloads = self._conversation_payloads(raw)
        conversations = []
        for payload in payloads:
            conversation = self._parse_conversation(payload)
            if conversation and conversation.messages:
                conversations.append(conversation)
        return conversations

    def _load_export(self, path: Path):
        if path.is_dir():
            return self._load_json_file(path / "conversations.json")
        if path.is_file() and path.suffix.lower() == ".zip":
            return self._load_zip_file(path)
        if path.is_file() and path.name == "conversations.json":
            return self._load_json_file(path)
        raise ValueError(f"Unsupported ChatGPT import path: {path}")

    @staticmethod
    def _load_json_file(path: Path):
        if not path.exists():
            raise FileNotFoundError(path)
        return json.loads(path.read_text(encoding="utf-8", errors="ignore"))

    @staticmethod
    def _load_zip_file(path: Path):
        with ZipFile(path) as archive:
            names = [
                name
                for name in archive.namelist()
                if name.endswith("conversations.json")
            ]
            if not names:
                raise FileNotFoundError("conversations.json not found in export zip")
            target = sorted(names, key=lambda name: (name.count("/"), len(name)))[0]
            with archive.open(target) as handle:
                return json.loads(handle.read().decode("utf-8", errors="ignore"))

    @staticmethod
    def _conversation_payloads(raw) -> list[dict]:
        if isinstance(raw, list):
            return [item for item in raw if isinstance(item, dict)]
        if isinstance(raw, dict):
            if isinstance(raw.get("conversations"), list):
                return [item for item in raw["conversations"] if isinstance(item, dict)]
            return [raw]
        raise ValueError("Unsupported ChatGPT export format")

    def _parse_conversation(self, payload: dict) -> Conversation | None:
        mapping = payload.get("mapping")
        if not isinstance(mapping, dict) or not mapping:
            return None

        messages = []
        for message_payload in self._message_payloads(payload):
            message = self._parse_message(message_payload)
            if message:
                messages.append(message)

        if not messages:
            return None

        conversation_id = self._conversation_id(payload)
        conversation = Conversation(
            id=conversation_id,
            tool="chatgpt",
            messages=messages,
            started_at=messages[0].timestamp
            or self._parse_timestamp(payload.get("create_time")),
            title=str(payload.get("title") or "").strip(),
        )
        if not conversation.title:
            conversation.title = conversation.auto_title()
        return conversation

    def _message_payloads(self, payload: dict) -> list[dict]:
        mapping = payload.get("mapping")
        if not isinstance(mapping, dict):
            return []

        active_ids = self._active_path_ids(mapping, payload.get("current_node"))
        if active_ids:
            nodes = [mapping[node_id] for node_id in active_ids if node_id in mapping]
        else:
            nodes = list(mapping.values())

        messages = []
        for node in nodes:
            if not isinstance(node, dict):
                continue
            message = node.get("message")
            if isinstance(message, dict):
                messages.append(message)

        if active_ids:
            return messages

        return sorted(messages, key=lambda item: self._timestamp_sort_key(item))

    @staticmethod
    def _active_path_ids(mapping: dict, current_node_id) -> list[str]:
        if not isinstance(current_node_id, str) or current_node_id not in mapping:
            return []

        path_ids = []
        seen = set()
        node_id = current_node_id
        while isinstance(node_id, str) and node_id in mapping and node_id not in seen:
            seen.add(node_id)
            path_ids.append(node_id)
            parent = mapping[node_id].get("parent")
            if not isinstance(parent, str):
                break
            node_id = parent

        path_ids.reverse()
        return path_ids

    def _parse_message(self, payload: dict) -> Message | None:
        metadata = (
            payload.get("metadata") if isinstance(payload.get("metadata"), dict) else {}
        )
        if metadata.get("is_visually_hidden_from_conversation"):
            return None
        if metadata.get("is_visibly_hidden_from_conversation"):
            return None

        author = (
            payload.get("author") if isinstance(payload.get("author"), dict) else {}
        )
        role = author.get("role")
        if role not in {"user", "assistant", "tool"}:
            return None

        content = self._extract_text(payload.get("content"))
        if not content:
            return None

        tool_name = None
        if role == "tool":
            recipient = payload.get("recipient")
            if isinstance(recipient, str) and recipient and recipient != "all":
                tool_name = recipient

        return Message(
            role=role,
            content=content,
            timestamp=self._parse_timestamp(
                payload.get("create_time") or payload.get("update_time")
            ),
            tool_name=tool_name,
        )

    def _extract_text(self, content) -> str:
        if isinstance(content, str):
            return content.strip()

        if not isinstance(content, dict):
            return ""

        chunks: list[str] = []
        parts = content.get("parts")
        if isinstance(parts, list):
            for part in parts:
                text = self._part_text(part)
                if text:
                    chunks.append(text)

        for key in ("text", "result", "user_instructions"):
            value = content.get(key)
            if isinstance(value, str) and value.strip():
                chunks.append(value.strip())

        joined = "\n\n".join(chunk for chunk in chunks if chunk)
        return joined.strip()

    def _part_text(self, part) -> str:
        if isinstance(part, str):
            return part.strip()
        if not isinstance(part, dict):
            return ""

        if isinstance(part.get("text"), str) and part["text"].strip():
            return part["text"].strip()
        if (
            isinstance(part.get("user_instructions"), str)
            and part["user_instructions"].strip()
        ):
            return part["user_instructions"].strip()
        if isinstance(part.get("asset_pointer"), str) and part["asset_pointer"].strip():
            return f"[asset: {part['asset_pointer'].strip()}]"
        if isinstance(part.get("content"), str) and part["content"].strip():
            return part["content"].strip()
        return ""

    @staticmethod
    def _parse_timestamp(value) -> datetime | None:
        if value is None:
            return None
        if isinstance(value, (int, float)):
            return datetime.fromtimestamp(value, tz=UTC)
        if isinstance(value, str):
            try:
                return datetime.fromtimestamp(float(value), tz=UTC)
            except ValueError:
                return None
        return None

    def _conversation_id(self, payload: dict) -> str:
        for key in ("id", "conversation_id"):
            value = payload.get(key)
            if isinstance(value, str) and value.strip():
                return value.strip()

        digest = hashlib.sha1(
            json.dumps(payload, ensure_ascii=False, sort_keys=True).encode("utf-8")
        ).hexdigest()
        return digest

    def _timestamp_sort_key(self, payload: dict):
        timestamp = self._parse_timestamp(
            payload.get("create_time") or payload.get("update_time")
        )
        return timestamp or datetime.min.replace(tzinfo=UTC)
