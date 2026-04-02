from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Optional

DEFAULT_MODEL = "openrouter/free"
DEFAULT_PROVIDER = "openrouter"
DEFAULT_OPENROUTER_BASE_URL = "https://openrouter.ai/api/v1"
DEFAULT_GEMINI_MODEL = "gemini-2.5-flash"
DEFAULT_GEMINI_BASE_URL = "https://generativelanguage.googleapis.com/v1beta/openai/"
DEFAULT_XAI_MODEL = "grok-4.20-beta-latest-non-reasoning"
DEFAULT_XAI_BASE_URL = "https://api.x.ai/v1"
SUPPORTED_PROVIDERS = ("openrouter", "openai", "gemini", "xai", "custom")
API_MODE_RESPONSES = "responses"
API_MODE_CHAT_COMPLETIONS = "chat_completions"


@dataclass(frozen=True)
class ProviderSettings:
    provider: str
    provider_name: str
    api_key_env: str
    api_key: Optional[str]
    base_url: Optional[str]
    api_mode: str
    supports_reasoning: bool
    default_headers: Optional[dict[str, str]] = None


def default_model_for_provider(provider: str) -> Optional[str]:
    if provider == "openrouter":
        return os.getenv("MINI_CODEX_MODEL", DEFAULT_MODEL)
    if provider == "openai":
        return os.getenv("OPENAI_MODEL") or os.getenv("MINI_CODEX_MODEL")
    if provider == "gemini":
        return os.getenv("GEMINI_MODEL") or os.getenv("MINI_CODEX_MODEL") or DEFAULT_GEMINI_MODEL
    if provider == "xai":
        return os.getenv("XAI_MODEL") or os.getenv("MINI_CODEX_MODEL") or DEFAULT_XAI_MODEL
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
            base_url=os.getenv("OPENROUTER_BASE_URL") or DEFAULT_OPENROUTER_BASE_URL,
            api_mode=API_MODE_RESPONSES,
            supports_reasoning=True,
            default_headers={"X-Title": "Mini Codex"},
        )

    if provider == "openai":
        return ProviderSettings(
            provider="openai",
            provider_name="OpenAI",
            api_key_env="OPENAI_API_KEY",
            api_key=os.getenv("OPENAI_API_KEY"),
            base_url=os.getenv("OPENAI_BASE_URL") or None,
            api_mode=API_MODE_RESPONSES,
            supports_reasoning=True,
        )

    if provider == "gemini":
        return ProviderSettings(
            provider="gemini",
            provider_name="Gemini",
            api_key_env="GEMINI_API_KEY",
            api_key=os.getenv("GEMINI_API_KEY"),
            base_url=os.getenv("GEMINI_BASE_URL") or DEFAULT_GEMINI_BASE_URL,
            api_mode=API_MODE_CHAT_COMPLETIONS,
            supports_reasoning=False,
        )

    if provider == "xai":
        return ProviderSettings(
            provider="xai",
            provider_name="xAI",
            api_key_env="XAI_API_KEY",
            api_key=os.getenv("XAI_API_KEY"),
            base_url=os.getenv("XAI_BASE_URL") or DEFAULT_XAI_BASE_URL,
            api_mode=API_MODE_RESPONSES,
            supports_reasoning=False,
        )

    if provider == "custom":
        return ProviderSettings(
            provider="custom",
            provider_name="Custom",
            api_key_env="MINI_CODEX_API_KEY",
            api_key=os.getenv("MINI_CODEX_API_KEY"),
            base_url=os.getenv("MINI_CODEX_BASE_URL") or None,
            api_mode=API_MODE_RESPONSES,
            supports_reasoning=True,
        )

    raise ValueError(f"unsupported provider: {provider}")
