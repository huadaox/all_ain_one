from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

from .models import Conversation, Message, _normalize_datetime


def render_conversation(conv: Conversation) -> str:
    """Render a conversation to markdown."""
    lines = []
    title = conv.auto_title()
    date_str = (
        conv.started_at.strftime("%Y-%m-%d %H:%M:%S") if conv.started_at else "Unknown"
    )

    lines.append(f"# {title}")
    lines.append("")
    lines.append(f"- **Tool**: {conv.tool}")
    if conv.project:
        lines.append(f"- **Project**: {conv.project}")
    lines.append(f"- **Session**: {conv.id}")
    lines.append(f"- **Started**: {date_str}")
    lines.append("")
    lines.append("---")
    lines.append("")

    for msg in conv.messages:
        ts = msg.timestamp.strftime("%H:%M:%S") if msg.timestamp else ""
        ts_suffix = f" ({ts})" if ts else ""

        if msg.role == "user":
            lines.append(f"## User{ts_suffix}")
            lines.append("")
            lines.append(msg.content)
            lines.append("")

        elif msg.role == "assistant":
            lines.append(f"## Assistant{ts_suffix}")
            lines.append("")
            lines.append(msg.content)
            lines.append("")

        elif msg.role == "tool":
            label = msg.tool_name or "tool"
            lines.append(f"### {label}{ts_suffix}")
            lines.append("")
            lines.append("```")
            lines.append(msg.content)
            lines.append("```")
            lines.append("")

    return "\n".join(lines)


def render_index(conversations: list[Conversation], output_dir: Path) -> str:
    """Render an index.md with links to all conversations."""
    lines = []
    lines.append("# AI Context Index")
    lines.append("")
    lines.append(f"Generated: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    lines.append("")

    # Group by tool
    by_tool: dict[str, list[Conversation]] = {}
    for conv in conversations:
        by_tool.setdefault(conv.tool, []).append(conv)

    for tool, convs in sorted(by_tool.items()):
        lines.append(f"## {tool} ({len(convs)} sessions)")
        lines.append("")
        # Sort by time descending
        convs.sort(
            key=lambda c: _normalize_datetime(c.started_at)
            if c.started_at
            else datetime.min.replace(tzinfo=UTC),
            reverse=True,
        )
        for conv in convs:
            date_str = (
                conv.started_at.strftime("%Y-%m-%d") if conv.started_at else "unknown"
            )
            filename = _conv_filename(conv)
            rel_path = f"{conv.tool}/{filename}"
            title = conv.auto_title()
            project_info = f" | `{conv.project}`" if conv.project else ""
            lines.append(f"- [{date_str} - {title}]({rel_path}){project_info}")
        lines.append("")

    return "\n".join(lines)


def _conv_filename(conv: Conversation) -> str:
    date_str = conv.started_at.strftime("%Y-%m-%d") if conv.started_at else "unknown"
    safe_id = conv.id[:16]
    return f"{date_str}_{safe_id}.md"


def save_conversations(conversations: list[Conversation], output_dir: Path):
    """Save all conversations as markdown files."""
    output_dir.mkdir(parents=True, exist_ok=True)

    for conv in conversations:
        tool_dir = output_dir / conv.tool
        tool_dir.mkdir(exist_ok=True)

        filename = _conv_filename(conv)
        md_content = render_conversation(conv)
        (tool_dir / filename).write_text(md_content, encoding="utf-8")

    # Write index
    index_content = render_index(conversations, output_dir)
    (output_dir / "index.md").write_text(index_content, encoding="utf-8")
