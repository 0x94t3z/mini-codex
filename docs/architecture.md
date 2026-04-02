# Architecture

Mini Codex is split into a few small modules so the CLI, tool execution, and
config stay easy to reason about.

## Main Flow

1. `main.py` loads the package CLI and keeps the direct-run path working.
2. `mini_codex.env` loads `.env` values without overwriting shell variables.
3. `mini_codex.providers` resolves provider defaults and connection settings.
4. `mini_codex.cli` reads CLI arguments and builds the agent.
5. `mini_codex.console` handles the welcome text, local commands, and local status responses.
6. `mini_codex.agent` handles the conversation loop and model/tool round trips.
7. `mini_codex.tools` contains all workspace file helpers and command helpers.

## Key Ideas

- The workspace is always scoped to the `--workdir` folder.
- File operations use dedicated helpers instead of raw shell commands.
- Tool calls are approved before writes, deletes, moves, and command execution
  unless `--auto-approve` is set.
- Conversation history is stored locally so stateless provider calls still feel
  like a normal chat session.
- OpenRouter, OpenAI, and xAI use the Responses API path, while Gemini uses the
  chat-completions path.

## Why This Layout

The current layout keeps the code easy to test and easy to change:

- `cli.py` stays focused on startup and user input.
- `console.py` keeps the local command and status behavior separate from argument parsing.
- `agent.py` stays focused on model orchestration.
- `providers.py` isolates provider-specific defaults and API wiring.
- `env.py` keeps `.env` parsing separate from application settings.
- `tools.py` stays focused on filesystem and command utilities.
- `config.py` keeps shared settings and prompts in one place.
