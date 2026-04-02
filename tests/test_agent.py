import sys
import unittest
from pathlib import Path
from types import SimpleNamespace

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
for candidate in (SRC, ROOT):
    if str(candidate) not in sys.path:
        sys.path.insert(0, str(candidate))

from mini_codex.agent import response_item_to_input_item  # noqa: E402


class AgentHelperTests(unittest.TestCase):
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


if __name__ == "__main__":
    unittest.main()
