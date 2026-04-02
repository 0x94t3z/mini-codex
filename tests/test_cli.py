import sys
import unittest
from contextlib import redirect_stdout
from io import StringIO
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
for candidate in (SRC, ROOT):
    if str(candidate) not in sys.path:
        sys.path.insert(0, str(candidate))

from mini_codex.cli import build_agent, parse_args  # noqa: E402


class CliTests(unittest.TestCase):
    def test_parse_args_uses_env_default_workdir(self) -> None:
        with patch.dict("os.environ", {"MINI_CODEX_WORKDIR": "./flask-ui"}, clear=False):
            args = parse_args([])
            self.assertEqual(args.workdir, "./flask-ui")

    def test_parse_args_cli_workdir_overrides_env(self) -> None:
        with patch.dict("os.environ", {"MINI_CODEX_WORKDIR": "./flask-ui"}, clear=False):
            args = parse_args(["--workdir", "./api-ui"])
            self.assertEqual(args.workdir, "./api-ui")

    def test_parse_args_uses_env_provider_and_model(self) -> None:
        with patch.dict(
            "os.environ",
            {
                "MINI_CODEX_PROVIDER": "openai",
                "OPENAI_MODEL": "gpt-test",
            },
            clear=False,
        ):
            args = parse_args([])
            self.assertEqual(args.provider, "openai")
            self.assertEqual(args.model, "gpt-test")

    @patch("mini_codex.cli.OpenAI")
    def test_build_agent_uses_openrouter_settings(self, mock_openai: object) -> None:
        with patch.dict(
            "os.environ",
            {
                "OPENROUTER_API_KEY": "router-key",
                "OPENROUTER_BASE_URL": "https://router.example/v1",
            },
            clear=False,
        ):
            args = parse_args([])
            agent = build_agent(args)

        mock_openai.assert_called_once_with(
            api_key="router-key",
            base_url="https://router.example/v1",
            default_headers={"X-Title": "Mini Codex"},
        )
        self.assertEqual(agent.config.provider_name, "OpenRouter")
        self.assertEqual(agent.config.model, "openrouter/free")

    @patch("mini_codex.cli.OpenAI")
    def test_build_agent_uses_openai_settings(self, mock_openai: object) -> None:
        with patch.dict(
            "os.environ",
            {
                "MINI_CODEX_PROVIDER": "openai",
                "OPENAI_API_KEY": "openai-key",
                "OPENAI_MODEL": "gpt-test",
            },
            clear=False,
        ):
            args = parse_args([])
            agent = build_agent(args)

        mock_openai.assert_called_once_with(api_key="openai-key")
        self.assertEqual(agent.config.provider_name, "OpenAI")
        self.assertEqual(agent.config.model, "gpt-test")

    @patch("mini_codex.cli.OpenAI")
    def test_build_agent_uses_custom_settings(self, mock_openai: object) -> None:
        with patch.dict(
            "os.environ",
            {
                "MINI_CODEX_PROVIDER": "custom",
                "MINI_CODEX_API_KEY": "custom-key",
                "MINI_CODEX_BASE_URL": "https://example.com/v1",
                "MINI_CODEX_MODEL": "custom-model",
            },
            clear=False,
        ):
            args = parse_args([])
            agent = build_agent(args)

        mock_openai.assert_called_once_with(
            api_key="custom-key",
            base_url="https://example.com/v1",
        )
        self.assertEqual(agent.config.provider_name, "Custom")
        self.assertEqual(agent.config.model, "custom-model")

    def test_parse_args_version_flag_prints_version(self) -> None:
        output = StringIO()
        with redirect_stdout(output):
            with self.assertRaises(SystemExit) as exc_info:
                parse_args(["--version"])

        self.assertEqual(exc_info.exception.code, 0)
        self.assertIn("Mini Codex 0.1.0", output.getvalue())


if __name__ == "__main__":
    unittest.main()
