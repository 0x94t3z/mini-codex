from __future__ import annotations

import argparse
import json
import os
import shlex
import subprocess
import sys
import threading
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Optional

try:
    from openai import OpenAI
except ImportError:  # pragma: no cover - exercised in runtime setup, not tests
    OpenAI = None  # type: ignore[assignment]


DEFAULT_MODEL = "openrouter/free"
DEFAULT_REASONING_EFFORT = "medium"
MAX_FILE_BYTES = 50_000
MAX_COMMAND_OUTPUT_CHARS = 12_000
MAX_TOOL_ROUNDS = 8
DEFAULT_OPENROUTER_BASE_URL = "https://openrouter.ai/api/v1"

SYSTEM_PROMPT = """
You are Mini Codex, a concise coding assistant that helps inside a local workspace.

Guidelines:
- Use tools when you need to inspect files, create files, or run commands.
- Prefer file tools for file tasks: use `read_file`, `write_file`, `delete_file`, `create_directory`, and `move_file` instead of shell commands.
- Use `run_command` only for real program execution, not for simple file operations.
- `run_command` does not support shell operators or redirection such as `|`, `&&`, `||`, `>`, `<`, or `2>/dev/null`.
- Tool arguments must match the schema exactly; use JSON numbers for numeric fields like `limit` and `timeout_seconds`.
- If a missing folder can be created safely to complete the request, create it instead of asking the user for permission first.
- Avoid repeated retries with slightly different tool arguments. Pick one valid tool call and continue from its result.
- Prefer small, deliberate steps and explain what you are doing.
- Never invent file contents when a tool can check them.
- When writing files, produce complete, runnable text.
- After successful tool use, always answer in plain, human-readable language.
- When a command fails, summarize the failure clearly and propose the next step.
- Stay inside the provided workspace and avoid destructive actions.
""".strip()


def load_dotenv_file(path: Path) -> None:
    if not path.exists() or not path.is_file():
        return

    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue

        if line.startswith("export "):
            line = line[len("export ") :].strip()

        if "=" not in line:
            continue

        key, value = line.split("=", 1)
        key = key.strip()
        value = value.strip()

        if not key or key in os.environ:
            continue

        if len(value) >= 2 and value[0] == value[-1] and value[0] in {'"', "'"}:
            value = value[1:-1]

        os.environ[key] = value


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
            "run_command does not support shell operators or redirection; use a plain executable and arguments"
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
                    "description": "Directory path relative to the workspace root. Use '.' for the root.",
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
        "description": "Move or rename a file inside the workspace. Creates parent directories when needed.",
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


@dataclass
class AppConfig:
    model: str
    workdir: Path
    auto_approve: bool
    reasoning_effort: str
    max_tool_rounds: int
    provider_name: str


def response_item_to_input_item(item: Any) -> Optional[dict[str, Any]]:
    item_type = getattr(item, "type", None)

    if item_type == "message":
        content_blocks = []
        for block in getattr(item, "content", []):
            if getattr(block, "type", None) == "output_text":
                content_blocks.append(
                    {
                        "type": "input_text",
                        "text": getattr(block, "text", ""),
                    }
                )

        if not content_blocks:
            return None

        return {
            "type": "message",
            "role": getattr(item, "role", "assistant"),
            "content": content_blocks,
        }

    if item_type == "function_call":
        parsed_arguments, error = parse_tool_arguments(getattr(item, "arguments", ""))
        if error is not None or parsed_arguments is None:
            return None
        return {
            "type": "function_call",
            "call_id": getattr(item, "call_id"),
            "name": getattr(item, "name"),
            "arguments": json.dumps(parsed_arguments, separators=(",", ":")),
        }

    return None


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
        return f"Moving {arguments.get('source_path', 'file')} to {arguments.get('destination_path', 'destination')}"
    if name == "run_command":
        return f"Running {arguments.get('command', 'command')}"
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


class MiniCodex:
    def __init__(self, client: Any, config: AppConfig) -> None:
        self.client = client
        self.config = config
        self.history: list[dict[str, Any]] = []

    def reset(self) -> None:
        self.history = []

    def ask(self, user_message: str) -> str:
        working_items = [*self.history, {"role": "user", "content": user_message}]
        response = self._create_response(input_items=working_items)
        recent_tool_results: list[tuple[str, dict[str, Any]]] = []

        rounds = 0
        while True:
            function_calls = [item for item in response.output if item.type == "function_call"]
            if not function_calls:
                final_text = response.output_text.strip() or summarize_tool_results(recent_tool_results)
                self.history.extend(
                    [
                        {"role": "user", "content": user_message},
                        {"role": "assistant", "content": final_text},
                    ]
                )
                return final_text

            rounds += 1
            if rounds > self.config.max_tool_rounds:
                return "Mini Codex stopped because it exceeded the tool-call limit for one turn."

            response_inputs = []
            for item in response.output:
                normalized = response_item_to_input_item(item)
                if normalized is not None:
                    response_inputs.append(normalized)

            tool_outputs = []
            for item in function_calls:
                parsed_arguments, parse_error = parse_tool_arguments(item.arguments)
                if parse_error is None and parsed_arguments is not None:
                    print(f"Mini Codex> {describe_tool_call(item.name, parsed_arguments)}...")
                    tool_result = self._execute_tool(item.name, json.dumps(parsed_arguments))
                else:
                    print(f"Mini Codex> Skipping invalid tool call for {item.name}.")
                    tool_result = {"ok": False, "error": parse_error}

                recent_tool_results.append((item.name, tool_result))
                tool_outputs.append(
                    {
                        "type": "function_call_output",
                        "call_id": item.call_id,
                        "output": json.dumps(tool_result),
                    }
                )

            working_items = [*working_items, *response_inputs, *tool_outputs]
            response = self._create_response(input_items=working_items)

    def _create_response(
        self,
        input_items: list[dict[str, Any]],
    ) -> Any:
        request: dict[str, Any] = {
            "model": self.config.model,
            "instructions": SYSTEM_PROMPT,
            "input": input_items,
            "tools": TOOLS,
            "parallel_tool_calls": False,
            "reasoning": {"effort": self.config.reasoning_effort},
        }
        return self._create_response_with_timer(request)

    def _create_response_with_timer(self, request: dict[str, Any]) -> Any:
        result: dict[str, Any] = {"response": None, "error": None}

        def worker() -> None:
            try:
                result["response"] = self.client.responses.create(**request)
            except Exception as exc:  # pragma: no cover - exercised through integration flow
                result["error"] = exc

        thread = threading.Thread(target=worker, daemon=True)
        thread.start()

        started_at = time.monotonic()
        while thread.is_alive():
            elapsed_seconds = int(time.monotonic() - started_at)
            print(
                f"\rMini Codex is thinking... {format_elapsed(elapsed_seconds)}",
                end="",
                flush=True,
            )
            thread.join(timeout=1)

        print("\r" + (" " * 40) + "\r", end="", flush=True)

        if result["error"] is not None:
            raise result["error"]

        return result["response"]

    def _execute_tool(self, name: str, arguments_json: str) -> dict[str, Any]:
        arguments, parse_error = parse_tool_arguments(arguments_json)
        if parse_error is not None or arguments is None:
            return {"ok": False, "error": parse_error}

        try:
            if name == "list_files":
                return list_files(
                    self.config.workdir,
                    arguments["path"],
                    coerce_optional_int(arguments["limit"], "limit"),
                )

            if name == "read_file":
                return read_text_file(
                    self.config.workdir,
                    arguments["path"],
                    coerce_optional_int(arguments["start_line"], "start_line"),
                    coerce_optional_int(arguments["end_line"], "end_line"),
                )

            if name == "write_file":
                path = arguments["path"]
                if not self._confirm(f"Allow file write to {path}?"):
                    return {"ok": False, "error": f"user denied write access to {path}"}
                return write_text_file(self.config.workdir, path, arguments["content"])

            if name == "delete_file":
                path = arguments["path"]
                if not self._confirm(f"Allow file deletion of {path}?"):
                    return {"ok": False, "error": f"user denied deletion of {path}"}
                return delete_text_file(self.config.workdir, path)

            if name == "create_directory":
                path = arguments["path"]
                if not self._confirm(f"Allow folder creation for {path}?"):
                    return {"ok": False, "error": f"user denied folder creation for {path}"}
                return create_directory(self.config.workdir, path)

            if name == "move_file":
                source_path = arguments["source_path"]
                destination_path = arguments["destination_path"]
                if not self._confirm(f"Allow moving {source_path} to {destination_path}?"):
                    return {
                        "ok": False,
                        "error": f"user denied move from {source_path} to {destination_path}",
                    }
                return move_text_file(self.config.workdir, source_path, destination_path)

            if name == "run_command":
                command = arguments["command"]
                if not self._confirm(f"Allow command: {command}?"):
                    return {"ok": False, "error": f"user denied command: {command}"}
                return run_command(
                    self.config.workdir,
                    command,
                    coerce_optional_int(arguments["timeout_seconds"], "timeout_seconds"),
                )
        except Exception as exc:  # pragma: no cover - small wrapper around pure helpers
            return {"ok": False, "error": str(exc)}

        return {"ok": False, "error": f"unknown tool: {name}"}

    def _confirm(self, prompt: str) -> bool:
        if self.config.auto_approve:
            return True

        while True:
            answer = input(f"{prompt} [y/N] ").strip().lower()
            if answer in {"y", "yes"}:
                return True
            if answer in {"", "n", "no"}:
                return False
            print("Please answer with 'y' or 'n'.")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Mini Codex: a tiny coding assistant in your terminal.")
    parser.add_argument(
        "prompt",
        nargs="*",
        help="Optional one-shot prompt. If omitted, Mini Codex starts in interactive mode.",
    )
    parser.add_argument(
        "--model",
        default=os.getenv("MINI_CODEX_MODEL", DEFAULT_MODEL),
        help=f"Model to use. Default: {DEFAULT_MODEL}",
    )
    parser.add_argument(
        "--workdir",
        default=".",
        help="Workspace directory Mini Codex can inspect and edit.",
    )
    parser.add_argument(
        "--reasoning-effort",
        default=DEFAULT_REASONING_EFFORT,
        choices=["low", "medium", "high"],
        help="Reasoning effort to request from the model.",
    )
    parser.add_argument(
        "--max-tool-rounds",
        type=int,
        default=MAX_TOOL_ROUNDS,
        help="Maximum tool-call loops for a single user prompt.",
    )
    parser.add_argument(
        "--auto-approve",
        action="store_true",
        help="Automatically approve file writes and command execution.",
    )
    return parser.parse_args()


def ensure_runtime_ready() -> None:
    if OpenAI is None:
        print(
            "The OpenAI SDK is not installed. Run 'python3 -m pip install -r requirements.txt' first.",
            file=sys.stderr,
        )
        raise SystemExit(1)

    if not os.getenv("OPENROUTER_API_KEY"):
        print("OPENROUTER_API_KEY is not set.", file=sys.stderr)
        print("Example: export OPENROUTER_API_KEY='your_api_key_here'", file=sys.stderr)
        raise SystemExit(1)


def build_agent(args: argparse.Namespace) -> MiniCodex:
    ensure_runtime_ready()
    client = OpenAI(
        base_url=os.getenv("OPENROUTER_BASE_URL", DEFAULT_OPENROUTER_BASE_URL),
        api_key=os.getenv("OPENROUTER_API_KEY"),
        default_headers={
            "X-Title": "Mini Codex",
        },
    )
    config = AppConfig(
        model=args.model,
        workdir=Path(args.workdir).resolve(),
        auto_approve=args.auto_approve,
        reasoning_effort=args.reasoning_effort,
        max_tool_rounds=args.max_tool_rounds,
        provider_name="OpenRouter",
    )
    return MiniCodex(client, config)


def print_welcome(config: AppConfig) -> None:
    print("Mini Codex")
    print(f"provider: {config.provider_name}")
    print(f"workspace: {config.workdir}")
    print(f"model: {config.model}")
    print("commands: /help, /reset, /quit")


def handle_local_command(agent: MiniCodex, raw_text: str) -> bool:
    command = raw_text.strip().lower()
    if command in {"/quit", "\\quit"}:
        return False
    if command in {"/reset", "\\reset"}:
        agent.reset()
        print("Conversation state cleared.")
        return True
    if command in {"/help", "\\help"}:
        print("Type a coding request and press enter.")
        print("/reset clears the conversation.")
        print("/quit exits Mini Codex.")
        return True
    print(f"Unknown local command: {raw_text}")
    return True


def interactive_loop(agent: MiniCodex) -> None:
    print_welcome(agent.config)
    while True:
        try:
            user_message = input("\nYou> ").strip()
        except (EOFError, KeyboardInterrupt):
            print("\nBye.")
            return

        if not user_message:
            continue

        if user_message.startswith("/"):
            if not handle_local_command(agent, user_message):
                return
            continue

        try:
            answer = agent.ask(user_message)
        except Exception as exc:
            print(f"Mini Codex error: {exc}")
            continue

        print(f"\nMini Codex> {answer}")


def main() -> None:
    load_dotenv_file(Path(".env"))
    args = parse_args()
    agent = build_agent(args)

    if args.prompt:
        prompt = " ".join(args.prompt)
        print(agent.ask(prompt))
        return

    interactive_loop(agent)


if __name__ == "__main__":
    main()
