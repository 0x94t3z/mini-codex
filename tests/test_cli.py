import sys
import unittest
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
for candidate in (SRC, ROOT):
    if str(candidate) not in sys.path:
        sys.path.insert(0, str(candidate))

from mini_codex.cli import parse_args


class CliTests(unittest.TestCase):
    def test_parse_args_uses_env_default_workdir(self) -> None:
        with patch.dict("os.environ", {"MINI_CODEX_WORKDIR": "./flask-ui"}, clear=False):
            args = parse_args([])
            self.assertEqual(args.workdir, "./flask-ui")

    def test_parse_args_cli_workdir_overrides_env(self) -> None:
        with patch.dict("os.environ", {"MINI_CODEX_WORKDIR": "./flask-ui"}, clear=False):
            args = parse_args(["--workdir", "./api-ui"])
            self.assertEqual(args.workdir, "./api-ui")


if __name__ == "__main__":
    unittest.main()
