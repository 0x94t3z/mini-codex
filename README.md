# Mini Codex

Mini Codex is a small terminal coding assistant built with Python and the OpenAI SDK, configured to call OpenRouter's Responses API. It keeps conversation state locally between turns, can inspect files in a workspace, and asks before it writes files or runs commands.

## Features

- chat in the terminal
- list and read files inside a workspace
- create or overwrite text files after approval
- create folders and move files inside the workspace
- run non-shell commands like `python3 -m unittest` after approval
- continue a conversation across multiple turns
- use OpenRouter's free router by default
- show a simple elapsed timer while the model is thinking

## Quick Start

```bash
python3 -m venv .venv
source .venv/bin/activate
python3 -m pip install --upgrade pip setuptools wheel
python3 -m pip install -r requirements.lock.txt
python3 -m pip install -e ".[dev]"
cp .env.example .env
mini-codex
```

Set your key in `.env`:

```env
OPENROUTER_API_KEY="your_api_key_here"
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
```

3. Create a `.env` file:

```bash
cp .env.example .env
```

Then set your key in `.env`:

```env
OPENROUTER_API_KEY="your_api_key_here"
```

Optional:

```env
MINI_CODEX_MODEL="openrouter/free"
MINI_CODEX_WORKDIR="."
OPENROUTER_BASE_URL="https://openrouter.ai/api/v1"
```

## Run it

Interactive mode:

```bash
mini-codex
```

One-shot mode:

```bash
mini-codex "Create a hello world script"
```

Choose a workspace and model:

```bash
mini-codex --workdir . --model openrouter/free
```

Set a default workspace in `.env`:

```env
MINI_CODEX_WORKDIR="./flask-ui"
```

Then you can simply run:

```bash
mini-codex
```

And override it any time with:

```bash
mini-codex --workdir ./another-folder
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
Move hello.py to the generated folder
```

```text
Create a calculator script in generated/calculator.py
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
├── tests/
├── README.md
├── LICENSE
├── pyproject.toml
├── requirements.lock.txt
└── .env.example
```

## Notes

- File access is restricted to the workspace root you pass with `--workdir`.
- `run_command` uses argument parsing instead of a full shell, so operators like `|`, `&&`, and redirects are not supported.
- The default model is `openrouter/free`, which OpenRouter documents as a zero-cost router for currently available free models.
- OpenRouter's Responses API is treated as stateless here, so Mini Codex stores chat history locally and resends it each turn.
- If you want a specific free model instead of the router, pass a model like `some-provider/some-model:free`.
- `.env` is loaded automatically at startup, and existing shell environment variables still win if both are set.
- If you prefer not to install the CLI entry point, `python3 main.py` still works.
- `requirements.lock.txt` pins the runtime dependency versions used by the current build.
- `ruff` is configured in `pyproject.toml` and runs in CI.

## Safety

- File changes and destructive actions still require approval unless you use `--auto-approve`.
- The app keeps operations inside the selected workspace directory.
- `run_command` is intentionally limited and should not be treated as a full shell.

## License

This project is licensed under the MIT License. See [LICENSE](/Users/0xgets/Documents/Python/mini-codex/LICENSE).
