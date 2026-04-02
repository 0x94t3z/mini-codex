import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
for candidate in (SRC, ROOT):
    if str(candidate) not in sys.path:
        sys.path.insert(0, str(candidate))

from mini_codex.console import (  # noqa: E402
    format_status,
    looks_like_status_question,
    maybe_resolve_local_response,
)


class ConsoleTests(unittest.TestCase):
    def test_format_status_shows_runtime_details(self) -> None:
        agent = type(
            "Agent",
            (),
            {
                "config": type(
                    "Config",
                    (),
                    {
                        "provider_name": "OpenRouter",
                        "model": "openrouter/free",
                        "workdir": Path("/tmp/workspace"),
                    },
                )()
            },
        )()

        status = format_status(agent)
        self.assertIn("provider: OpenRouter", status)
        self.assertIn("model: openrouter/free", status)
        self.assertIn("workspace: /tmp/workspace", status)
        self.assertIn("route: OpenRouter free router", status)

    def test_looks_like_status_question_detects_meta_questions(self) -> None:
        self.assertTrue(looks_like_status_question("which model are you using?"))
        self.assertTrue(looks_like_status_question("what provider and model are we using"))
        self.assertFalse(looks_like_status_question("create a calculator in examples"))

    def test_maybe_resolve_local_response_handles_status_requests(self) -> None:
        agent = type(
            "Agent",
            (),
            {
                "config": type(
                    "Config",
                    (),
                    {
                        "provider_name": "OpenRouter",
                        "model": "openrouter/free",
                        "workdir": Path("/tmp/workspace"),
                    },
                )()
            },
        )()

        response = maybe_resolve_local_response(agent, "which model did you use now?")
        self.assertIsNotNone(response)
        self.assertIn("provider: OpenRouter", response)
        self.assertIn("model: openrouter/free", response)


if __name__ == "__main__":
    unittest.main()
