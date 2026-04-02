# Changelog

All notable changes to Mini Codex will be documented in this file.

## [Unreleased]

### Added

- `--version` in the CLI and a single version source in `src/mini_codex/version.py`.
- A local pre-commit setup for Ruff and the unit tests.
- A lightweight release workflow built around this changelog.

### Changed

- The package version is now sourced from `mini_codex.version.VERSION` instead of being duplicated.

## [0.1.0] - 2026-04-02

### Added

- Initial terminal coding assistant.
- OpenRouter-backed chat flow with local conversation history.
- Workspace file tools for listing, reading, writing, deleting, creating folders, and moving files.
- GitHub Actions workflow for test validation.
