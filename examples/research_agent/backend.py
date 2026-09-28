"""Read-only repository tools plus an in-memory write overlay, so the example never touches disk."""

import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from prompt_kit import ErrorKind, ToolError

SECRET_FILE_PATTERN = re.compile(r"(^|/)(\.env(\..*)?|secrets?/.*|.*\.(pem|key))$")
SKIPPED_DIRECTORIES = {".git", ".venv", "__pycache__", ".idea", "node_modules"}
MAX_MATCHES = 20

CANNED_WEB_RESULTS = [
    {
        "title": "asyncio.timeout - Python 3.13 documentation",
        "url": "https://docs.python.org/3.13/library/asyncio-task.html#asyncio.timeout",
        "snippet": "Return an asynchronous context manager that can be used to limit the time spent waiting.",
    }
]


@dataclass
class RepositoryBackend:
    root: Path
    written_files: dict[str, str] = field(default_factory=dict)

    def _resolve(self, path: str) -> Path:
        resolved = (self.root / path).resolve()
        if not resolved.is_relative_to(self.root.resolve()):
            raise ToolError(
                ErrorKind.INVALID_INPUT, hint="Paths must stay inside the repository."
            )
        if SECRET_FILE_PATTERN.search(
            resolved.relative_to(self.root.resolve()).as_posix()
        ):
            raise ToolError("secret_file_request", path=path)
        return resolved

    def _source_files(self) -> list[Path]:
        return [
            path
            for path in sorted(self.root.rglob("*"))
            if path.is_file()
            and not SKIPPED_DIRECTORIES.intersection(path.relative_to(self.root).parts)
            and not SECRET_FILE_PATTERN.search(path.relative_to(self.root).as_posix())
        ]

    async def search_code(self, query: str) -> dict[str, Any]:
        try:
            pattern = re.compile(query)
        except re.error as error:
            raise ToolError(
                ErrorKind.INVALID_INPUT, hint=f"Invalid regular expression: {error}"
            ) from error
        matches = []
        for path in self._source_files():
            try:
                lines = path.read_text(encoding="utf-8").splitlines()
            except UnicodeDecodeError:
                continue
            for line_number, line in enumerate(lines, start=1):
                if pattern.search(line):
                    matches.append(
                        {
                            "path": path.relative_to(self.root).as_posix(),
                            "line": line_number,
                            "text": line.strip(),
                        }
                    )
                    if len(matches) == MAX_MATCHES:
                        return {"matches": matches, "truncated": True}
        return {"matches": matches, "truncated": False}

    async def read_file(
        self, path: str, start_line: int, max_lines: int
    ) -> dict[str, Any]:
        resolved = self._resolve(path)
        if path in self.written_files:
            content = self.written_files[path]
        elif resolved.is_file():
            content = resolved.read_text(encoding="utf-8")
        else:
            raise ToolError(
                ErrorKind.NOT_FOUND, hint="Use search_code to find the right path."
            )
        if start_line < 1 or max_lines < 1:
            raise ToolError(
                ErrorKind.INVALID_INPUT,
                hint="start_line and max_lines must be at least 1.",
            )
        lines = content.splitlines()
        end_line = min(start_line - 1 + max_lines, len(lines))
        selected = range(start_line, end_line + 1)
        result = {
            "path": path,
            "total_lines": len(lines),
            "content": "\n".join(
                f"{number:>4}  {lines[number - 1]}" for number in selected
            ),
            "truncated": end_line < len(lines),
        }
        if result["truncated"]:
            result["next_start_line"] = end_line + 1
        return result

    async def web_search(self, query: str) -> dict[str, Any]:
        return {"results": CANNED_WEB_RESULTS}

    async def write_file(
        self, path: str, content: str, idempotency_key: str
    ) -> dict[str, Any]:
        self._resolve(path)
        self.written_files[path] = content
        return {"path": path, "bytes_written": len(content.encode())}

    def implementations(self) -> dict[str, Any]:
        return {
            "search_code": self.search_code,
            "read_file": self.read_file,
            "web_search": self.web_search,
            "write_file": self.write_file,
        }
