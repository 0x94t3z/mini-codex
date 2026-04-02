# Architecture

Mini Codex is split into a few small modules so the CLI, tool execution, and
config stay easy to reason about.

## Main Flow

1. `main.py` loads the package CLI and keeps the direct-run path working.
2. `mini_codex.cli` loads `.env`, reads CLI arguments, and builds the agent.
3. `mini_codex.agent` handles the conversation loop and model/tool round trips.
4. `mini_codex.tools` contains all workspace file helpers and command helpers.

## Key Ideas

- The workspace is always scoped to the `--workdir` folder.
- File operations use dedicated helpers instead of raw shell commands.
- Tool calls are approved before writes, deletes, moves, and command execution
  unless `--auto-approve` is set.
- Conversation history is stored locally so stateless provider calls still feel
  like a normal chat session.

## Why This Layout

The current layout keeps the code easy to test and easy to change:

- `cli.py` stays focused on startup and user input.
- `agent.py` stays focused on model orchestration.
- `tools.py` stays focused on filesystem and command utilities.
- `config.py` keeps shared settings and prompts in one place.
