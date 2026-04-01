import tempfile
import unittest
from os import environ
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from main import (
    coerce_optional_int,
    create_directory,
    delete_text_file,
    describe_tool_call,
    format_elapsed,
    list_files,
    load_dotenv_file,
    move_text_file,
    parse_tool_arguments,
    read_text_file,
    resolve_workspace_path,
    response_item_to_input_item,
    run_command,
    summarize_tool_results,
    write_text_file,
)


class WorkspaceToolTests(unittest.TestCase):
    def test_resolve_workspace_path_allows_nested_paths(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            workdir = Path(tmp)
            resolved = resolve_workspace_path(workdir, "src/app.py")
            self.assertEqual(resolved, (workdir / "src" / "app.py").resolve())

    def test_resolve_workspace_path_blocks_escape(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            workdir = Path(tmp)
            with self.assertRaises(ValueError):
                resolve_workspace_path(workdir, "../outside.txt")

    def test_write_and_read_file(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            workdir = Path(tmp)
            write_result = write_text_file(workdir, "notes.txt", "alpha\nbeta\ngamma\n")
            self.assertTrue(write_result["ok"])

            read_result = read_text_file(workdir, "notes.txt", 2, 3)
            self.assertEqual(read_result["start_line"], 2)
            self.assertEqual(read_result["end_line"], 3)
            self.assertIn("2: beta", read_result["content"])
            self.assertIn("3: gamma", read_result["content"])

    def test_delete_file_removes_file(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            workdir = Path(tmp)
            write_text_file(workdir, "hello.py", "print('hi')\n")

            result = delete_text_file(workdir, "hello.py")
            self.assertTrue(result["ok"])
            self.assertTrue(result["deleted"])
            self.assertFalse((workdir / "hello.py").exists())

    def test_create_directory_creates_nested_folder(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            workdir = Path(tmp)
            result = create_directory(workdir, "generated/scripts")
            self.assertTrue(result["ok"])
            self.assertTrue((workdir / "generated" / "scripts").is_dir())

    def test_move_file_moves_and_creates_parent_folder(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            workdir = Path(tmp)
            write_text_file(workdir, "hello.py", "print('hi')\n")

            result = move_text_file(workdir, "hello.py", "generated/hello.py")
            self.assertTrue(result["ok"])
            self.assertFalse((workdir / "hello.py").exists())
            self.assertTrue((workdir / "generated" / "hello.py").exists())

    def test_list_files_returns_relative_paths(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            workdir = Path(tmp)
            write_text_file(workdir, "a.txt", "a")
            write_text_file(workdir, "nested/b.txt", "b")

            result = list_files(workdir, ".", 10)
            self.assertEqual(result["path"], ".")
            self.assertIn("a.txt", result["files"])
            self.assertIn("nested/b.txt", result["files"])

    def test_run_command_captures_output(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            workdir = Path(tmp)
            result = run_command(workdir, "python3 -c \"print('hello')\"", 5)
            self.assertTrue(result["ok"])
            self.assertEqual(result["exit_code"], 0)
            self.assertIn("hello", result["stdout"])

    def test_coerce_optional_int_accepts_numeric_strings(self) -> None:
        self.assertEqual(coerce_optional_int("50", "limit"), 50)
        self.assertEqual(coerce_optional_int(5, "timeout_seconds"), 5)
        self.assertIsNone(coerce_optional_int(None, "timeout_seconds"))

    def test_format_elapsed_uses_minutes_and_seconds(self) -> None:
        self.assertEqual(format_elapsed(0), "00:00")
        self.assertEqual(format_elapsed(5), "00:05")
        self.assertEqual(format_elapsed(65), "01:05")

    def test_describe_tool_call_is_human_readable(self) -> None:
        message = describe_tool_call(
            "move_file",
            {"source_path": "hello.py", "destination_path": "generated/hello.py"},
        )
        self.assertEqual(message, "Moving hello.py to generated/hello.py")

    def test_summarize_tool_results_returns_human_summary(self) -> None:
        summary = summarize_tool_results(
            [
                ("create_directory", {"ok": True, "path": "generated", "created": True}),
                (
                    "move_file",
                    {
                        "ok": True,
                        "source_path": "hello.py",
                        "destination_path": "generated/hello.py",
                        "moved": True,
                    },
                ),
            ]
        )
        self.assertIn("Created folder `generated`.", summary)
        self.assertIn("Moved `hello.py` to `generated/hello.py`.", summary)

    def test_parse_tool_arguments_parses_json_object(self) -> None:
        parsed, error = parse_tool_arguments('{"path":"hello.py"}')
        self.assertEqual(parsed, {"path": "hello.py"})
        self.assertIsNone(error)

    def test_parse_tool_arguments_rejects_invalid_json(self) -> None:
        parsed, error = parse_tool_arguments('{"path":"hello.py"')
        self.assertIsNone(parsed)
        self.assertIn("tool arguments were not valid JSON", error)

    def test_response_message_is_normalized_for_stateless_history(self) -> None:
        item = SimpleNamespace(
            type="message",
            role="assistant",
            content=[SimpleNamespace(type="output_text", text="hello from router")],
        )

        normalized = response_item_to_input_item(item)
        self.assertEqual(normalized["type"], "message")
        self.assertEqual(normalized["role"], "assistant")
        self.assertEqual(
            normalized["content"],
            [{"type": "input_text", "text": "hello from router"}],
        )

    def test_function_call_is_normalized_for_stateless_history(self) -> None:
        item = SimpleNamespace(
            type="function_call",
            call_id="call_123",
            name="read_file",
            arguments='{"path":"main.py","start_line":1,"end_line":5}',
        )

        normalized = response_item_to_input_item(item)
        self.assertEqual(normalized["type"], "function_call")
        self.assertEqual(normalized["call_id"], "call_123")
        self.assertEqual(normalized["name"], "read_file")
        self.assertEqual(normalized["arguments"], '{"path":"main.py","start_line":1,"end_line":5}')

    def test_invalid_function_call_is_dropped_from_history(self) -> None:
        item = SimpleNamespace(
            type="function_call",
            call_id="call_bad",
            name="read_file",
            arguments='{"path":"main.py"',
        )

        normalized = response_item_to_input_item(item)
        self.assertIsNone(normalized)

    def test_load_dotenv_file_reads_values(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            dotenv_path = Path(tmp) / ".env"
            dotenv_path.write_text(
                "# comment\nOPENROUTER_API_KEY=\"test-key\"\nexport MINI_CODEX_MODEL=openrouter/free\n",
                encoding="utf-8",
            )

            with patch.dict(environ, {}, clear=False):
                load_dotenv_file(dotenv_path)
                self.assertEqual(environ["OPENROUTER_API_KEY"], "test-key")
                self.assertEqual(environ["MINI_CODEX_MODEL"], "openrouter/free")

    def test_load_dotenv_file_does_not_override_existing_values(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            dotenv_path = Path(tmp) / ".env"
            dotenv_path.write_text("OPENROUTER_API_KEY=from-file\n", encoding="utf-8")

            with patch.dict(environ, {"OPENROUTER_API_KEY": "from-shell"}, clear=False):
                load_dotenv_file(dotenv_path)
                self.assertEqual(environ["OPENROUTER_API_KEY"], "from-shell")


if __name__ == "__main__":
    unittest.main()
