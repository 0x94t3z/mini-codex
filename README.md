# Mini Codex

Mini Codex is a terminal coding assistant for working inside a scoped
workspace. It starts on OpenRouter, but you can switch to OpenAI, Gemini, xAI,
or another OpenAI-compatible provider with environment variables or
`--provider`.

It keeps conversation state locally between turns, can inspect files in the
selected workspace, and asks before it writes files or runs commands.

## Features

- Terminal chat with multi-turn context
- Workspace-aware file browsing and editing
- Approval-gated writes, deletes, folder creation, and file moves
- Safe command execution for non-shell tools like `python3 -m unittest`
- OpenRouter by default, with provider switching for OpenAI, Gemini, xAI, or custom OpenAI-compatible endpoints
- A simple elapsed timer while the model is thinking
- `mini-codex --version` for quick version checks

## Quick Start

```bash
python3 -m venv .venv
source .venv/bin/activate
python3 -m pip install --upgrade pip setuptools wheel
python3 -m pip install -r requirements.lock.txt
python3 -m pip install -e ".[dev]"
pre-commit install
cp .env.example .env
mini-codex
```

Set your key in `.env`:

```env
OPENROUTER_API_KEY="your_api_key_here"
```

To use OpenAI instead of OpenRouter:

```env
MINI_CODEX_PROVIDER="openai"
OPENAI_API_KEY="your_openai_api_key_here"
OPENAI_MODEL="your-openai-model-id"
```

To use Gemini instead of OpenRouter:

```env
MINI_CODEX_PROVIDER="gemini"
GEMINI_API_KEY="your_gemini_api_key_here"
GEMINI_MODEL="gemini-2.5-flash"
```

To use xAI instead of OpenRouter:

```env
MINI_CODEX_PROVIDER="xai"
XAI_API_KEY="your_xai_api_key_here"
XAI_MODEL="grok-4.20-beta-latest-non-reasoning"
```

## Setup

1. Create and activate a virtual environment:

```bash
python3 -m venv .venv
source .venv/bin/activate
```

2. Install dependencies:

```bash
python3 -m pip install --upgrade pip setuptools wheel
python3 -m pip install -r requirements.lock.txt
python3 -m pip install -e ".[dev]"
pre-commit install
```

You can run the full hook set anytime with:

```bash
pre-commit run --all-files
```

3. Create a `.env` file:

```bash
cp .env.example .env
```

Then set your key in `.env`:

```env
OPENROUTER_API_KEY="your_api_key_here"
```

Optional settings:

```env
MINI_CODEX_PROVIDER="openrouter"
MINI_CODEX_MODEL="openrouter/free"
MINI_CODEX_WORKDIR="."
OPENROUTER_BASE_URL="https://openrouter.ai/api/v1"
```

`MINI_CODEX_WORKDIR` is the default folder Mini Codex works in when you do not
pass `--workdir`. For example, if you set:

```env
MINI_CODEX_WORKDIR="./examples"
```

then running `mini-codex` will open that folder by default.

## Run it

Interactive mode:

```bash
mini-codex
```

One-shot mode:

```bash
mini-codex "Create a hello world script"
```

Work inside the bundled examples workspace:

```bash
mini-codex --workdir ./examples --model openrouter/free
```

Choose a provider:

```bash
mini-codex --provider openai --model your-openai-model-id
```

```bash
mini-codex --provider gemini --model gemini-2.5-flash
```

```bash
mini-codex --provider xai --model grok-4.20-beta-latest-non-reasoning
```

Set a default workspace in `.env`:

```env
MINI_CODEX_WORKDIR="./examples"
```

Then you can simply run:

```bash
mini-codex
```

And override it any time with another folder, like `./docs`:

```bash
mini-codex --workdir ./docs
```

Skip approval prompts:

```bash
mini-codex --auto-approve
```

If `pip install -e .` fails on an older Python or pip build, use the direct fallback:

```bash
python3 -m pip install -r requirements.txt
python3 main.py
```

## Example Prompts

```text
Create a hello world script
```

```text
Move hello.py to the examples folder
```

```text
Create a calculator script in examples/calculator.py
```

```text
Read main.py and explain how tool approvals work
```

## Local commands

- `/help`
- `/reset`
- `/quit`
- `\help`
- `\reset`
- `\quit`

## Project Layout

```text
mini-codex/
├── src/
│   └── mini_codex/
│       ├── agent.py
│       ├── cli.py
│       ├── config.py
│       └── tools.py
├── main.py
├── examples/
│   └── README.md
├── tests/
├── README.md
├── docs/
│   ├── README.md
│   └── architecture.md
│   └── usage.md
├── LICENSE
├── pyproject.toml
├── requirements.lock.txt
└── .env.example
```

## Notes

- File access is restricted to the workspace root you pass with `--workdir`.
- `run_command` uses argument parsing instead of a full shell, so operators like `|`, `&&`, and redirects are not supported.
- The default model is `openrouter/free`, which OpenRouter documents as a zero-cost router for currently available free models.
- You can switch providers with `MINI_CODEX_PROVIDER` or `--provider`. OpenAI
  uses `OPENAI_API_KEY` and `OPENAI_MODEL`, Gemini uses `GEMINI_API_KEY` and
  `GEMINI_MODEL`, xAI uses `XAI_API_KEY` and `XAI_MODEL`, and other
  OpenAI-compatible providers can use `MINI_CODEX_API_KEY`,
  `MINI_CODEX_BASE_URL`, and `MINI_CODEX_MODEL`.
- OpenRouter, OpenAI, and xAI use the Responses API path here, while Gemini
  uses the chat-completions path.
- If you want a specific free model instead of the router, pass the exact
  OpenRouter model name, such as `provider/model:free`.
- `.env` is loaded automatically at startup, and existing shell environment variables still win if both are set.
- If you prefer not to install the CLI entry point, `python3 main.py` still works.
- `requirements.lock.txt` pins the runtime dependency versions used by the current build.
- `ruff` is configured in `pyproject.toml` for local checks.
- `pre-commit` runs Ruff and the unit tests before commits.
- `pre-commit run --all-files` is a handy one-shot check before pushing.
- `examples/` is the bundled sample workspace folder for this repo.
- `examples/README.md` explains the included sample files and how to use them.
- `docs/` is for higher-level project notes, starting with the architecture overview.
- `docs/usage.md` shows a few concrete Mini Codex workflows.
- `MINI_CODEX_PROVIDER="openai"` switches the app to OpenAI, and `MINI_CODEX_PROVIDER="custom"` supports any OpenAI-compatible endpoint.
- Release notes live in [CHANGELOG.md](CHANGELOG.md).

## Safety

- File changes and destructive actions still require approval unless you use `--auto-approve`.
- The app keeps operations inside the selected workspace directory.
- `run_command` is intentionally limited and should not be treated as a full shell.

## License

This project is licensed under the MIT License. See [LICENSE](LICENSE).
