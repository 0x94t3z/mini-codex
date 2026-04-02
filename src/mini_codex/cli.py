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
    AppConfig,
    DEFAULT_MODEL,
    DEFAULT_OPENROUTER_BASE_URL,
    DEFAULT_REASONING_EFFORT,
    MAX_TOOL_ROUNDS,
    load_dotenv_file,
)


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

        if user_message.startswith("/") or user_message.startswith("\\"):
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
