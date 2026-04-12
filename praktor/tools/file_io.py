import asyncio
import json
from pathlib import Path

from core.tool import ToolResult, register_tool
from settings import MD, create_log

log = create_log()


def _resolve_path(filename: str) -> Path:
    if MD:
        return Path(MD) / filename
    return Path(filename)


class ReadFileTool:
    """
    Read a markdown file from the configured MD directory.

    Input: filename (e.g. "resume.md"). Relative to the MD env path.
    """

    name = "read_file"
    description = (
        "Read a markdown file. "
        "Input: filename relative to the MD directory (e.g. 'resume.md')."
    )

    async def __call__(self, input: str) -> ToolResult:
        path = _resolve_path(input.strip())
        try:
            content = await asyncio.to_thread(path.read_text, encoding="utf-8")
            return ToolResult(content=content, metadata={"path": str(path)})
        except FileNotFoundError:
            return ToolResult(content="", error=f"File not found: {path}")
        except Exception as e:
            log.error(f"ReadFileTool failed for '{input}': {e}")
            return ToolResult(content="", error=str(e))


class WriteFileTool:
    """
    Write content to a markdown file in the configured MD directory.

    Input: JSON string with keys "filename" and "content".
    Example: {"filename": "cover_letter.md", "content": "Dear hiring manager..."}
    """

    name = "write_file"
    description = (
        "Write content to a markdown file. "
        'Input: JSON with "filename" and "content" keys. '
        'Example: {"filename": "cover_letter.md", "content": "..."}'
    )

    async def __call__(self, input: str) -> ToolResult:
        try:
            data = json.loads(input)
            filename = data["filename"]
            content = data["content"]
        except (json.JSONDecodeError, KeyError) as e:
            return ToolResult(content="", error=f"Invalid input: {e}")

        path = _resolve_path(filename)
        try:
            await asyncio.to_thread(path.write_text, content, encoding="utf-8")
            return ToolResult(
                content=f"Written to {path}",
                metadata={"path": str(path), "bytes": len(content)},
            )
        except Exception as e:
            log.error(f"WriteFileTool failed for '{filename}': {e}")
            return ToolResult(content="", error=str(e))


# Auto-register at import time
register_tool(ReadFileTool())
register_tool(WriteFileTool())
