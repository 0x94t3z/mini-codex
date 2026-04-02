from __future__ import annotations

import json
import shlex
import subprocess
from pathlib import Path
from typing import Any, Optional

MAX_FILE_BYTES = 50_000
MAX_COMMAND_OUTPUT_CHARS = 12_000


def resolve_workspace_path(workdir: Path, raw_path: str) -> Path:
    workspace_root = workdir.resolve()
    candidate = Path(raw_path).expanduser()
    if not candidate.is_absolute():
        candidate = (workspace_root / candidate).resolve()
    else:
        candidate = candidate.resolve()

    try:
        candidate.relative_to(workspace_root)
    except ValueError as exc:
        raise ValueError(f"path must stay inside the workspace: {raw_path}") from exc

    return candidate


def truncate_text(text: str, limit: int) -> str:
    if len(text) <= limit:
        return text
    return text[:limit] + f"\n...[truncated {len(text) - limit} characters]"


def format_elapsed(seconds: int) -> str:
    minutes, remaining_seconds = divmod(max(0, seconds), 60)
    return f"{minutes:02d}:{remaining_seconds:02d}"


def coerce_optional_int(value: Any, field_name: str) -> Optional[int]:
    if value is None:
        return None
    if isinstance(value, int):
        return value
    if isinstance(value, str) and not value.strip():
        return None
    if isinstance(value, str) and value.strip().isdigit():
        return int(value.strip())
    raise ValueError(f"{field_name} must be an integer or null")


def parse_tool_arguments(arguments_json: str) -> tuple[Optional[dict[str, Any]], Optional[str]]:
    try:
        parsed = json.loads(arguments_json)
    except json.JSONDecodeError as exc:
        return None, f"tool arguments were not valid JSON: {exc}"

    if not isinstance(parsed, dict):
        return None, "tool arguments must decode to a JSON object"

    return parsed, None


def list_files(workdir: Path, relative_path: str, limit: Optional[int]) -> dict[str, Any]:
    workspace_root = workdir.resolve()
    target = resolve_workspace_path(workdir, relative_path or ".")
    if not target.exists():
        raise FileNotFoundError(f"path does not exist: {relative_path}")
    if not target.is_dir():
        raise NotADirectoryError(f"path is not a directory: {relative_path}")

    max_entries = limit or 200
    files: list[str] = []

    for path in sorted(target.rglob("*")):
        if len(files) >= max_entries:
            break
        if path.is_file():
            files.append(str(path.relative_to(workspace_root)))

    return {
        "ok": True,
        "path": str(target.relative_to(workspace_root)),
        "files": files,
        "truncated": len(files) >= max_entries,
    }


def read_text_file(
    workdir: Path,
    relative_path: str,
    start_line: Optional[int],
    end_line: Optional[int],
) -> dict[str, Any]:
    workspace_root = workdir.resolve()
    target = resolve_workspace_path(workdir, relative_path)
    if not target.exists():
        raise FileNotFoundError(f"file does not exist: {relative_path}")
    if not target.is_file():
        raise IsADirectoryError(f"path is not a file: {relative_path}")

    raw_bytes = target.read_bytes()
    if len(raw_bytes) > MAX_FILE_BYTES:
        raise ValueError(
            f"file is too large to read safely ({len(raw_bytes)} bytes > {MAX_FILE_BYTES} bytes)"
        )

    text = raw_bytes.decode("utf-8")
    lines = text.splitlines()

    if start_line is None and end_line is None:
        selected = lines
        selected_start = 1 if lines else 0
        selected_end = len(lines)
    else:
        start = 1 if start_line is None else max(1, start_line)
        end = len(lines) if end_line is None else max(start, end_line)
        selected = lines[start - 1 : end]
        selected_start = start
        selected_end = min(end, len(lines))

    numbered = "\n".join(
        f"{line_number:>4}: {line}"
        for line_number, line in enumerate(selected, start=selected_start)
    )

    return {
        "ok": True,
        "path": str(target.relative_to(workspace_root)),
        "start_line": selected_start,
        "end_line": selected_end,
        "content": numbered,
    }


def write_text_file(workdir: Path, relative_path: str, content: str) -> dict[str, Any]:
    workspace_root = workdir.resolve()
    target = resolve_workspace_path(workdir, relative_path)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(content, encoding="utf-8")
    return {
        "ok": True,
        "path": str(target.relative_to(workspace_root)),
        "bytes_written": len(content.encode("utf-8")),
    }


def create_directory(workdir: Path, relative_path: str) -> dict[str, Any]:
    workspace_root = workdir.resolve()
    target = resolve_workspace_path(workdir, relative_path)
    target.mkdir(parents=True, exist_ok=True)
    return {
        "ok": True,
        "path": str(target.relative_to(workspace_root)),
        "created": True,
    }


def delete_text_file(workdir: Path, relative_path: str) -> dict[str, Any]:
    workspace_root = workdir.resolve()
    target = resolve_workspace_path(workdir, relative_path)
    if not target.exists():
        raise FileNotFoundError(f"file does not exist: {relative_path}")
    if not target.is_file():
        raise IsADirectoryError(f"path is not a file: {relative_path}")

    target.unlink()
    return {
        "ok": True,
        "path": str(target.relative_to(workspace_root)),
        "deleted": True,
    }


def move_text_file(workdir: Path, source_path: str, destination_path: str) -> dict[str, Any]:
    workspace_root = workdir.resolve()
    source = resolve_workspace_path(workdir, source_path)
    destination = resolve_workspace_path(workdir, destination_path)
    if not source.exists():
        raise FileNotFoundError(f"file does not exist: {source_path}")
    if not source.is_file():
        raise IsADirectoryError(f"path is not a file: {source_path}")

    destination.parent.mkdir(parents=True, exist_ok=True)
    source.replace(destination)
    return {
        "ok": True,
        "source_path": str(source.relative_to(workspace_root)),
        "destination_path": str(destination.relative_to(workspace_root)),
        "moved": True,
    }


def run_command(workdir: Path, command: str, timeout_seconds: Optional[int]) -> dict[str, Any]:
    unsupported_tokens = ["|", "&&", "||", ">", "<"]
    if any(token in command for token in unsupported_tokens):
        raise ValueError(
            "run_command does not support shell operators or redirection; use a "
            "plain executable and arguments"
        )

    parts = shlex.split(command)
    if not parts:
        raise ValueError("command cannot be empty")

    timeout = timeout_seconds or 20

    try:
        completed = subprocess.run(
            parts,
            cwd=workdir,
            capture_output=True,
            text=True,
            timeout=timeout,
            check=False,
        )
    except subprocess.TimeoutExpired as exc:
        stdout = exc.stdout or ""
        stderr = exc.stderr or ""
        return {
            "ok": False,
            "command": command,
            "exit_code": None,
            "timed_out": True,
            "stdout": truncate_text(stdout, MAX_COMMAND_OUTPUT_CHARS),
            "stderr": truncate_text(stderr, MAX_COMMAND_OUTPUT_CHARS),
        }

    return {
        "ok": completed.returncode == 0,
        "command": command,
        "exit_code": completed.returncode,
        "timed_out": False,
        "stdout": truncate_text(completed.stdout, MAX_COMMAND_OUTPUT_CHARS),
        "stderr": truncate_text(completed.stderr, MAX_COMMAND_OUTPUT_CHARS),
    }


TOOLS: list[dict[str, Any]] = [
    {
        "type": "function",
        "name": "list_files",
        "description": "List files inside the workspace so you can inspect the project structure.",
        "strict": True,
        "parameters": {
            "type": "object",
            "properties": {
                "path": {
                    "type": "string",
                    "description": "Directory path relative to the workspace root. "
                    "Use '.' for the root.",
                },
                "limit": {
                    "type": ["integer", "null"],
                    "description": "Maximum number of files to return.",
                },
            },
            "required": ["path", "limit"],
            "additionalProperties": False,
        },
    },
    {
        "type": "function",
        "name": "read_file",
        "description": "Read a UTF-8 text file from the workspace, with optional line boundaries.",
        "strict": True,
        "parameters": {
            "type": "object",
            "properties": {
                "path": {
                    "type": "string",
                    "description": "File path relative to the workspace root.",
                },
                "start_line": {
                    "type": ["integer", "null"],
                    "description": "1-based starting line number, or null to start at the top.",
                },
                "end_line": {
                    "type": ["integer", "null"],
                    "description": "1-based ending line number, or null to read through the end.",
                },
            },
            "required": ["path", "start_line", "end_line"],
            "additionalProperties": False,
        },
    },
    {
        "type": "function",
        "name": "write_file",
        "description": "Create or overwrite a UTF-8 text file inside the workspace.",
        "strict": True,
        "parameters": {
            "type": "object",
            "properties": {
                "path": {
                    "type": "string",
                    "description": "File path relative to the workspace root.",
                },
                "content": {
                    "type": "string",
                    "description": "Complete file contents to write.",
                },
            },
            "required": ["path", "content"],
            "additionalProperties": False,
        },
    },
    {
        "type": "function",
        "name": "delete_file",
        "description": "Delete a UTF-8 text file inside the workspace.",
        "strict": True,
        "parameters": {
            "type": "object",
            "properties": {
                "path": {
                    "type": "string",
                    "description": "File path relative to the workspace root.",
                },
            },
            "required": ["path"],
            "additionalProperties": False,
        },
    },
    {
        "type": "function",
        "name": "create_directory",
        "description": "Create a directory inside the workspace.",
        "strict": True,
        "parameters": {
            "type": "object",
            "properties": {
                "path": {
                    "type": "string",
                    "description": "Directory path relative to the workspace root.",
                },
            },
            "required": ["path"],
            "additionalProperties": False,
        },
    },
    {
        "type": "function",
        "name": "move_file",
        "description": "Move or rename a file inside the workspace. Creates parent "
        "directories when needed.",
        "strict": True,
        "parameters": {
            "type": "object",
            "properties": {
                "source_path": {
                    "type": "string",
                    "description": "Existing file path relative to the workspace root.",
                },
                "destination_path": {
                    "type": "string",
                    "description": "New file path relative to the workspace root.",
                },
            },
            "required": ["source_path", "destination_path"],
            "additionalProperties": False,
        },
    },
    {
        "type": "function",
        "name": "run_command",
        "description": (
            "Run a workspace command without shell operators. Use plain executable + arguments, "
            "for example 'python3 -m unittest'."
        ),
        "strict": True,
        "parameters": {
            "type": "object",
            "properties": {
                "command": {
                    "type": "string",
                    "description": "Executable and arguments as one string.",
                },
                "timeout_seconds": {
                    "type": ["integer", "null"],
                    "description": "Command timeout in seconds.",
                },
            },
            "required": ["command", "timeout_seconds"],
            "additionalProperties": False,
        },
    },
]


def describe_tool_call(name: str, arguments: dict[str, Any]) -> str:
    if name == "list_files":
        return f"Looking at files in {arguments.get('path', '.')}"
    if name == "read_file":
        return f"Reading {arguments.get('path', 'file')}"
    if name == "write_file":
        return f"Writing {arguments.get('path', 'file')}"
    if name == "delete_file":
        return f"Deleting {arguments.get('path', 'file')}"
    if name == "create_directory":
        return f"Creating folder {arguments.get('path', 'folder')}"
    if name == "move_file":
        source = arguments.get("source_path", "file")
        destination = arguments.get("destination_path", "destination")
        return f"Moving {source} to {destination}"
    if name == "run_command":
        command = arguments.get("command", "command")
        return f"Running {command}"
    return f"Using tool {name}"


def summarize_tool_results(tool_results: list[tuple[str, dict[str, Any]]]) -> str:
    successful_lines: list[str] = []
    failed_lines: list[str] = []

    for name, result in tool_results:
        if result.get("ok"):
            if name == "write_file":
                successful_lines.append(f"Created or updated `{result['path']}`.")
            elif name == "delete_file":
                successful_lines.append(f"Deleted `{result['path']}`.")
            elif name == "create_directory":
                successful_lines.append(f"Created folder `{result['path']}`.")
            elif name == "move_file":
                successful_lines.append(
                    f"Moved `{result['source_path']}` to `{result['destination_path']}`."
                )
            elif name == "run_command":
                successful_lines.append("Ran the requested command.")
        else:
            error = result.get("error", "unknown error")
            failed_lines.append(f"`{name}` failed: {error}")

    if successful_lines:
        return " ".join(successful_lines + failed_lines).strip()
    if failed_lines:
        return " ".join(failed_lines).strip()
    return "Done."
