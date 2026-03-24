from .claude_code import ClaudeCodeExtractor, OpenCodeExtractor
from .cursor import CursorExtractor

EXTRACTORS = {
    "claude-code": ClaudeCodeExtractor,
    "opencode": OpenCodeExtractor,
    "cursor": CursorExtractor,
}
