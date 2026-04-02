from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

DEFAULT_MODEL = "openrouter/free"
DEFAULT_PROVIDER = "openrouter"
DEFAULT_REASONING_EFFORT = "medium"
MAX_TOOL_ROUNDS = 8
DEFAULT_OPENROUTER_BASE_URL = "https://openrouter.ai/api/v1"
SUPPORTED_PROVIDERS = ("openrouter", "openai", "custom")

SYSTEM_PROMPT = """
You are Mini Codex, a concise coding assistant that helps inside a local workspace.

Guidelines:
- Use tools when you need to inspect files, create files, or run commands.
- Prefer file tools for file tasks: use `read_file`, `write_file`, `delete_file`.
- Use `create_directory` and `move_file` for folder and file moves.
- Use `run_command` only for real program execution, not for simple file operations.
- `run_command` does not support shell operators or redirection like `|`, `&&`,
  `||`, `>`, `<`, or `2>/dev/null`.
- Tool arguments must match the schema exactly; use JSON numbers for numeric
  fields like `limit` and `timeout_seconds`.
- If a missing folder can be created safely to complete the request, create it.
- Avoid repeated retries with slightly different tool arguments.
- Pick one valid tool call and continue.
- Prefer small, deliberate steps and explain what you are doing.
- Never invent file contents when a tool can check them.
- When writing files, produce complete, runnable text.
- After successful tool use, always answer in plain, human-readable language.
- When a command fails, summarize the failure clearly and propose the next step.
- Stay inside the provided workspace and avoid destructive actions.
""".strip()


@dataclass
class AppConfig:
    model: str
    workdir: Path
    auto_approve: bool
    reasoning_effort: str
    max_tool_rounds: int
    provider_name: str


@dataclass(frozen=True)
class ProviderSettings:
    provider: str
    provider_name: str
    api_key_env: str
    api_key: Optional[str]
    base_url: Optional[str]
    default_headers: Optional[dict[str, str]] = None


def default_model_for_provider(provider: str) -> Optional[str]:
    if provider == "openrouter":
        return os.getenv("MINI_CODEX_MODEL", DEFAULT_MODEL)
    if provider == "openai":
        return os.getenv("OPENAI_MODEL")
    if provider == "custom":
        return os.getenv("MINI_CODEX_MODEL") or os.getenv("CUSTOM_MODEL")
    raise ValueError(f"unsupported provider: {provider}")


def resolve_provider_settings(provider: str) -> ProviderSettings:
    if provider == "openrouter":
        return ProviderSettings(
            provider="openrouter",
            provider_name="OpenRouter",
            api_key_env="OPENROUTER_API_KEY",
            api_key=os.getenv("OPENROUTER_API_KEY"),
            base_url=os.getenv("OPENROUTER_BASE_URL", DEFAULT_OPENROUTER_BASE_URL),
            default_headers={"X-Title": "Mini Codex"},
        )

    if provider == "openai":
        return ProviderSettings(
            provider="openai",
            provider_name="OpenAI",
            api_key_env="OPENAI_API_KEY",
            api_key=os.getenv("OPENAI_API_KEY"),
            base_url=os.getenv("OPENAI_BASE_URL") or None,
        )

    if provider == "custom":
        return ProviderSettings(
            provider="custom",
            provider_name="Custom",
            api_key_env="MINI_CODEX_API_KEY",
            api_key=os.getenv("MINI_CODEX_API_KEY"),
            base_url=os.getenv("MINI_CODEX_BASE_URL") or None,
        )

    raise ValueError(f"unsupported provider: {provider}")


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
