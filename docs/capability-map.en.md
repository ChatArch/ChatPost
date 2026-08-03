# Capability Map

Use this page to check which first-class capabilities `ChatPost` currently owns, which ones are verified, and what remains out of scope for this package.

## Capability Groups

<div class="grid cards" markdown>

- **CLI Entry**

    `chatpost --help` and `chatpost --version` are the default verification entry points.

- **Python API**

    Substantive behavior should live in importable Python functions, classes, or service layers rather than only in Click callbacks.

- **Config and Environment**

    ChatEnv integration is enabled by default; stable, shared configuration belongs in `config.py`.

- **Browser Runner Design**

    A host-binary, Docker, multi-account user-data-dir, and bridge isolation proposal exists; runner commands are not implemented.

</div>

## Current Boundary

| Capability | Status | Notes |
| --- | --- | --- |
| CLI base entry | Implemented | The template generates a Click group, `--version`, and a base test. |
| ChatEnv provider | Implemented | The template generates `config.py` and a `chatenv.configs` entry point. |
| CLI structure design | Proposed | Runner/account/plan/draft/publication boundaries are documented, but the commands do not exist. |
| Browser runners and account isolation | Proposed | Host binary by default and one user-data-dir/bridge per runner; not implemented. |
| Business commands | Not implemented | Add these from the real package domain; do not fake future commands in the template. |

## Out of Scope

- No plan placeholder page is generated.
- No unimplemented capability should be written as a user operation tutorial.
- Commands in design documents remain explicitly proposed until code, tests, and help text exist.
- No secret, token, cookie, or Authorization header should appear in README, docs, issues, PR comments, or CI logs.
