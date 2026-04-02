from __future__ import annotations

import json
import threading
import time
from typing import Any, Optional

from .config import AppConfig, SYSTEM_PROMPT
from .tools import (
    TOOLS,
    coerce_optional_int,
    create_directory,
    delete_text_file,
    describe_tool_call,
    format_elapsed,
    list_files,
    move_text_file,
    parse_tool_arguments,
    read_text_file,
    run_command,
    summarize_tool_results,
    write_text_file,
)


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
            "call_id": item.call_id,
            "name": item.name,
            "arguments": json.dumps(parsed_arguments, separators=(",", ":")),
        }

    return None


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
                final_text = response.output_text.strip() or summarize_tool_results(
                    recent_tool_results
                )
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

    def _create_response(self, input_items: list[dict[str, Any]]) -> Any:
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
