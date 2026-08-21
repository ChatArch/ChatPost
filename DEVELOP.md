# Development Guide

## CLI Rules

- Use `chatstyle>=0.2.0,<0.3.0` and `chatenv>=0.2.10,<0.3.0` as the canonical CLI/config runtime.
- Keep the root Click group explicitly named `chatpost` and use ChatStyle `add_tree_option()` for `--tree` and `--tree-brief`; do not add a package-local tree renderer.
- Prefer `CommandSchema`, `CommandField`, `add_interactive_option()`, and `resolve_command_inputs()` for new commands.
- Missing required args should auto-enter interactive mode when recoverable.
- `-i` forces interactive mode; `-I` disables prompting and must fail fast.
- Prompt defaults must match actual execution defaults.
- Sensitive values must stay masked in prompts and summaries.
- Prefer lazy imports in CLI wiring and keep implementation imports local when possible.

## Docs and Tests

- Use doc-first CLI testing.
- Put real CLI coverage under `tests/cli-tests/`.
- Put mock/fake CLI coverage under `tests/mock-cli-tests/`.
- Keep full and brief CLI tree docs synchronized with the registered command surface.
- Keep `README.md`, `docs/`, and `CHANGELOG.md` in sync with user-facing changes.

## Automation

- Keep automation small and reviewable.
- Prefer commands that can run in CI without interactive prompts.
- Ensure generated defaults are safe for local development.
