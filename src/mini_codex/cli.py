from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

try:
    from openai import OpenAI
except ImportError:  # pragma: no cover - exercised in runtime setup, not tests
    OpenAI = None  # type: ignore[assignment]

from .agent import MiniCodex
from .config import (
    DEFAULT_PROVIDER,
    DEFAULT_REASONING_EFFORT,
    MAX_TOOL_ROUNDS,
    SUPPORTED_PROVIDERS,
    AppConfig,
    default_model_for_provider,
    load_dotenv_file,
    resolve_provider_settings,
)
from .version import VERSION

STATUS_QUERIES = (
    "which model are you using",
    "what model are you using",
    "which provider are you using",
    "what provider are you using",
    "which model did you use",
    "what model did you use",
    "which provider did you use",
    "what provider and model are we using",
    "what provider and model are you using",
    "what are you using",
    "what is that",
    "who are you",
    "tell me about yourself",
)


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    bootstrap = argparse.ArgumentParser(add_help=False)
    bootstrap.add_argument(
        "--provider",
        default=os.getenv("MINI_CODEX_PROVIDER", DEFAULT_PROVIDER),
        choices=SUPPORTED_PROVIDERS,
    )
    bootstrap_args, _ = bootstrap.parse_known_args(argv)
    model_default = default_model_for_provider(bootstrap_args.provider)

    parser = argparse.ArgumentParser(
        description="Mini Codex: a tiny coding assistant in your terminal.",
        epilog=(
            "Providers:\n"
            "  openrouter  Default option. Uses OpenRouter's free router.\n"
            "  openai      Use OpenAI with OPENAI_API_KEY and OPENAI_MODEL.\n"
            "  gemini      Use Gemini with GEMINI_API_KEY and GEMINI_MODEL.\n"
            "  xai         Use xAI with XAI_API_KEY and XAI_MODEL.\n"
            "  custom      Use any OpenAI-compatible endpoint.\n\n"
            "Examples:\n"
            "  mini-codex --provider openrouter --model openrouter/free\n"
            "  mini-codex --provider openai --model gpt-4.1\n"
            "  mini-codex --provider gemini --model gemini-2.5-flash\n"
            "  mini-codex --provider xai --model grok-4.20-beta-latest-non-reasoning"
        ),
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument(
        "prompt",
        nargs="*",
        help="Optional one-shot prompt. If omitted, Mini Codex starts in interactive mode.",
    )
    parser.add_argument(
        "--provider",
        default=bootstrap_args.provider,
        choices=SUPPORTED_PROVIDERS,
        help="Provider to use. Default: openrouter.",
    )
    parser.add_argument(
        "--model",
        default=model_default,
        help="Model to use. Use --provider plus the matching API key for other providers.",
    )
    parser.add_argument(
        "--workdir",
        default=os.getenv("MINI_CODEX_WORKDIR", "."),
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
    parser.add_argument(
        "--version",
        action="version",
        version=f"Mini Codex {VERSION}",
    )
    return parser.parse_args(argv)


def ensure_runtime_ready() -> None:
    if OpenAI is None:
        print(
            "The OpenAI SDK is not installed. Run "
            "'python3 -m pip install -r requirements.txt' first.",
            file=sys.stderr,
        )
        raise SystemExit(1)


def build_agent(args: argparse.Namespace) -> MiniCodex:
    ensure_runtime_ready()
    settings = resolve_provider_settings(args.provider)

    if not settings.api_key:
        print(f"{settings.api_key_env} is not set.", file=sys.stderr)
        raise SystemExit(1)
    if settings.provider == "custom" and not settings.base_url:
        print("MINI_CODEX_BASE_URL is not set.", file=sys.stderr)
        raise SystemExit(1)
    if not args.model:
        print(
            f"{settings.provider_name} requires a model. Set --model or the matching "
            "provider model env var.",
            file=sys.stderr,
        )
        raise SystemExit(1)

    client_kwargs: dict[str, object] = {"api_key": settings.api_key}
    if settings.base_url:
        client_kwargs["base_url"] = settings.base_url
    if settings.default_headers:
        client_kwargs["default_headers"] = settings.default_headers

    client = OpenAI(**client_kwargs)
    config = AppConfig(
        model=args.model,
        workdir=Path(args.workdir).resolve(),
        auto_approve=args.auto_approve,
        reasoning_effort=args.reasoning_effort,
        max_tool_rounds=args.max_tool_rounds,
        provider_name=settings.provider_name,
        api_mode=settings.api_mode,
        supports_reasoning=settings.supports_reasoning,
    )
    return MiniCodex(client, config)


def print_welcome(config: AppConfig) -> None:
    print("Mini Codex")
    print(f"provider: {config.provider_name}")
    print(f"workspace: {config.workdir}")
    print(f"model: {config.model}")
    print("commands: /help, /reset, /status, /quit")


def format_status(agent: MiniCodex) -> str:
    config = agent.config
    lines = [
        f"provider: {config.provider_name}",
        f"model: {config.model}",
        f"workspace: {config.workdir}",
    ]
    if config.provider_name == "OpenRouter":
        lines.append("route: OpenRouter free router or your selected OpenRouter model")
    elif config.provider_name == "Gemini":
        lines.append("route: Gemini chat-completions endpoint")
    elif config.provider_name == "xAI":
        lines.append("route: xAI Responses endpoint")
    elif config.provider_name == "OpenAI":
        lines.append("route: OpenAI Responses endpoint")
    else:
        lines.append("route: custom OpenAI-compatible endpoint")
    return "\n".join(lines)


def looks_like_status_question(text: str) -> bool:
    normalized = " ".join(text.strip().lower().split())
    return any(query in normalized for query in STATUS_QUERIES)


def maybe_resolve_local_response(agent: MiniCodex, raw_text: str) -> str | None:
    if looks_like_status_question(raw_text):
        return format_status(agent)
    return None


def handle_local_command(agent: MiniCodex, raw_text: str) -> bool:
    command = raw_text.strip().lower()
    if command in {"/quit", "\\quit"}:
        return False
    if command in {"/reset", "\\reset"}:
        agent.reset()
        print("Conversation state cleared.")
        return True
    if command in {"/status", "\\status", "/about", "\\about"}:
        print(format_status(agent))
        return True
    if command in {"/help", "\\help"}:
        print("Type a coding request and press enter.")
        print("/reset clears the conversation.")
        print("/status shows the configured provider, model, and workspace.")
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

        if user_message.startswith("/") or user_message.startswith("\\"):
            if not handle_local_command(agent, user_message):
                return
            continue

        local_response = maybe_resolve_local_response(agent, user_message)
        if local_response is not None:
            print(local_response)
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
        local_response = maybe_resolve_local_response(agent, prompt)
        if local_response is not None:
            print(local_response)
            return
        print(agent.ask(prompt))
        return

    interactive_loop(agent)
