from __future__ import annotations

import json
import threading
import time
from typing import Any, Callable, Optional

from .config import SYSTEM_PROMPT, AppConfig
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
        if self.config.api_mode == "chat_completions":
            return self._ask_chat(user_message)
        return self._ask_responses(user_message)

    def _ask_responses(self, user_message: str) -> str:
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

    def _ask_chat(self, user_message: str) -> str:
        working_messages = [*self.history, {"role": "user", "content": user_message}]
        response = self._create_chat_response(messages=working_messages)
        recent_tool_results: list[tuple[str, dict[str, Any]]] = []

        rounds = 0
        while True:
            choice = response.choices[0]
            message = choice.message
            tool_calls = list(getattr(message, "tool_calls", []) or [])
            if not tool_calls:
                final_text = self._content_to_text(getattr(message, "content", "")).strip() or (
                    summarize_tool_results(recent_tool_results)
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

            assistant_item = self._assistant_message_to_history_item(message)
            if assistant_item is not None:
                working_messages.append(assistant_item)

            tool_messages = []
            for tool_call in tool_calls:
                function = getattr(tool_call, "function", None)
                parsed_arguments, parse_error = parse_tool_arguments(
                    getattr(function, "arguments", "")
                )
                tool_name = getattr(function, "name", "unknown")
                if parse_error is None and parsed_arguments is not None:
                    print(f"Mini Codex> {describe_tool_call(tool_name, parsed_arguments)}...")
                    tool_result = self._execute_tool(tool_name, json.dumps(parsed_arguments))
                else:
                    print(f"Mini Codex> Skipping invalid tool call for {tool_name}.")
                    tool_result = {"ok": False, "error": parse_error}

                recent_tool_results.append((tool_name, tool_result))
                tool_messages.append(
                    {
                        "role": "tool",
                        "tool_call_id": tool_call.id,
                        "content": json.dumps(tool_result),
                    }
                )

            working_messages.extend(tool_messages)
            response = self._create_chat_response(messages=working_messages)

    def _create_response(self, input_items: list[dict[str, Any]]) -> Any:
        request: dict[str, Any] = {
            "model": self.config.model,
            "instructions": SYSTEM_PROMPT,
            "input": input_items,
            "tools": TOOLS,
            "parallel_tool_calls": False,
        }
        if self.config.supports_reasoning:
            request["reasoning"] = {"effort": self.config.reasoning_effort}
        return self._call_with_timer(lambda: self.client.responses.create(**request))

    def _create_chat_response(self, messages: list[dict[str, Any]]) -> Any:
        request: dict[str, Any] = {
            "model": self.config.model,
            "messages": messages,
            "tools": TOOLS,
        }
        if self.config.supports_reasoning:
            request["reasoning"] = {"effort": self.config.reasoning_effort}
        return self._call_with_timer(lambda: self.client.chat.completions.create(**request))

    def _call_with_timer(self, call: Callable[[], Any]) -> Any:
        result: dict[str, Any] = {"value": None, "error": None}

        def worker() -> None:
            try:
                result["value"] = call()
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

        return result["value"]

    def _assistant_message_to_history_item(self, message: Any) -> dict[str, Any]:
        content = self._content_to_text(getattr(message, "content", ""))
        history_item: dict[str, Any] = {"role": "assistant", "content": content}

        tool_calls = []
        for tool_call in getattr(message, "tool_calls", []) or []:
            function = getattr(tool_call, "function", None)
            tool_calls.append(
                {
                    "id": getattr(tool_call, "id", None),
                    "type": "function",
                    "function": {
                        "name": getattr(function, "name", ""),
                        "arguments": getattr(function, "arguments", ""),
                    },
                }
            )

        if tool_calls:
            history_item["tool_calls"] = tool_calls

        return history_item

    def _content_to_text(self, content: Any) -> str:
        if content is None:
            return ""
        if isinstance(content, str):
            return content
        if isinstance(content, list):
            parts: list[str] = []
            for block in content:
                block_type = getattr(block, "type", None)
                if block_type in {"output_text", "input_text"}:
                    parts.append(getattr(block, "text", ""))
                elif isinstance(block, dict) and block.get("type") in {"output_text", "input_text"}:
                    parts.append(str(block.get("text", "")))
            return "".join(parts)
        return str(content)

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
