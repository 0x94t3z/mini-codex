from __future__ import annotations

from typing import Protocol

from .config import AppConfig

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


class ConsoleAgent(Protocol):
    config: AppConfig

    def reset(self) -> None: ...


def print_welcome(config: AppConfig) -> None:
    print("Mini Codex")
    print(f"provider: {config.provider_name}")
    print(f"workspace: {config.workdir}")
    print(f"model: {config.model}")
    print("commands: /help, /reset, /status, /quit")


def format_status(agent: ConsoleAgent) -> str:
    config = agent.config
    lines = [
        f"provider: {config.provider_name}",
        f"model: {config.model}",
        f"workspace: {config.workdir}",
    ]
    if config.provider_name == "OpenRouter":
        lines.append("route: OpenRouter free router")
    elif config.provider_name == "Gemini":
        lines.append("route: Gemini chat-completions")
    elif config.provider_name == "xAI":
        lines.append("route: xAI Responses")
    elif config.provider_name == "OpenAI":
        lines.append("route: OpenAI Responses")
    else:
        lines.append("route: custom endpoint")
    return "\n".join(lines)


def looks_like_status_question(text: str) -> bool:
    normalized = " ".join(text.strip().lower().split())
    return any(query in normalized for query in STATUS_QUERIES)


def maybe_resolve_local_response(agent: ConsoleAgent, raw_text: str) -> str | None:
    if looks_like_status_question(raw_text):
        return format_status(agent)
    return None


def handle_local_command(agent: ConsoleAgent, raw_text: str) -> bool:
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
