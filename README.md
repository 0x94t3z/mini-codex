# Mini Codex

Mini Codex is a small terminal coding assistant built with Python and the OpenAI SDK, configured to call OpenRouter's Responses API. It keeps conversation state locally between turns, can inspect files in a workspace, and asks before it writes files or runs commands.

## What it can do

- chat in the terminal
- list and read files inside a workspace
- create or overwrite text files after approval
- run non-shell commands like `python3 -m unittest` after approval
- continue a conversation across multiple turns
- use OpenRouter's free router by default

## Setup

1. Create and activate a virtual environment:

```bash
python3 -m venv .venv
source .venv/bin/activate
```

2. Install dependencies:

```bash
python3 -m pip install --upgrade pip setuptools wheel
python3 -m pip install -e .
```

3. Create a `.env` file:

```bash
cp .env.example .env
```

Then set your key in `.env`:

```env
OPENROUTER_API_KEY="your_api_key_here"
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

Skip approval prompts:

```bash
mini-codex --auto-approve
```

If `pip install -e .` fails on an older Python or pip build, use the direct fallback:

```bash
python3 -m pip install -r requirements.txt
python3 main.py
```

## Local commands

- `/help`
- `/reset`
- `/quit`

## Notes

- File access is restricted to the workspace root you pass with `--workdir`.
- `run_command` uses argument parsing instead of a full shell, so operators like `|`, `&&`, and redirects are not supported.
- The default model is `openrouter/free`, which OpenRouter documents as a zero-cost router for currently available free models.
- OpenRouter's Responses API is treated as stateless here, so Mini Codex stores chat history locally and resends it each turn.
- If you want a specific free model instead of the router, pass a model like `some-provider/some-model:free`.
- `.env` is loaded automatically at startup, and existing shell environment variables still win if both are set.
- If you prefer not to install the CLI entry point, `python3 main.py` still works.
