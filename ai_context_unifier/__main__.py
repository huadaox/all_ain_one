"""AI Context Unifier - Unify AI tool conversations into markdown files."""

import argparse
import sys
from datetime import UTC, datetime, timedelta
from pathlib import Path

from .core.models import _normalize_datetime
from .extractors import EXTRACTORS
from .importers import IMPORTERS
from .core.renderer import save_conversations


def parse_since(value: str) -> datetime:
    """Parse a relative time string like '7d', '24h', '30m'."""
    units = {"d": "days", "h": "hours", "m": "minutes"}
    unit = value[-1]
    if unit not in units:
        raise ValueError(f"Unknown time unit: {unit}. Use d/h/m.")
    amount = int(value[:-1])
    return datetime.now(UTC) - timedelta(**{units[unit]: amount})


def main():
    parser = argparse.ArgumentParser(description="AI Context Unifier")
    sub = parser.add_subparsers(dest="command")

    sync_parser = sub.add_parser("sync", help="Extract and save conversations")
    sync_parser.add_argument(
        "-o", "--output", default="./ai-context-output", help="Output directory"
    )
    sync_parser.add_argument(
        "--since", help="Only extract recent conversations (e.g. 7d, 24h)"
    )
    sync_parser.add_argument(
        "--tool", action="append", help="Only extract from specific tools"
    )
    sync_parser.add_argument(
        "--no-tools", action="store_true", help="Exclude tool call details"
    )

    sub.add_parser("list", help="List available conversations")

    import_parser = sub.add_parser("import", help="Import official export files")
    import_parser.add_argument("provider", choices=sorted(IMPORTERS.keys()))
    import_parser.add_argument(
        "input", help="Export zip, directory, or conversations.json"
    )
    import_parser.add_argument(
        "-o", "--output", default="./ai-context-output", help="Output directory"
    )

    args = parser.parse_args()

    if not args.command:
        parser.print_help()
        sys.exit(1)

    if args.command == "import":
        importer = IMPORTERS[args.provider]()
        conversations = importer.import_path(Path(args.input))
        print(f"[{args.provider}] Found {len(conversations)} conversations")
        output_dir = Path(args.output)
        save_conversations(conversations, output_dir)
        print(f"\nSaved {len(conversations)} conversations to {output_dir}/")
        print(f"Index: {output_dir}/index.md")
        return

    since = parse_since(args.since) if hasattr(args, "since") and args.since else None
    tools = (
        args.tool if hasattr(args, "tool") and args.tool else list(EXTRACTORS.keys())
    )

    all_conversations = []
    for tool_name in tools:
        if tool_name not in EXTRACTORS:
            print(
                f"Unknown tool: {tool_name}. Available: {', '.join(EXTRACTORS.keys())}"
            )
            continue

        extractor = EXTRACTORS[tool_name]()
        if since:
            convs = extractor.extract_since(since)
        else:
            convs = extractor.extract()
        print(f"[{tool_name}] Found {len(convs)} conversations")
        all_conversations.extend(convs)

    if args.command == "list":
        all_conversations.sort(
            key=lambda c: _normalize_datetime(c.started_at)
            if c.started_at
            else datetime.min.replace(tzinfo=UTC),
            reverse=True,
        )
        for conv in all_conversations:
            date_str = (
                conv.started_at.strftime("%Y-%m-%d %H:%M")
                if conv.started_at
                else "unknown"
            )
            print(f"  {conv.tool:12s} | {date_str} | {conv.auto_title()[:60]}")
        return

    output_dir = Path(args.output)
    save_conversations(all_conversations, output_dir)
    print(f"\nSaved {len(all_conversations)} conversations to {output_dir}/")
    print(f"Index: {output_dir}/index.md")


if __name__ == "__main__":
    main()
