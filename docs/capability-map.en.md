# Capability Map

Use this page to check which first-class capabilities `ChatPost` currently owns, which ones are verified, and what remains out of scope for this package.

## Capability Groups

<div class="grid cards" markdown>

- **CLI Entry**

    `chatpost --help` and `chatpost --version` are the default verification entry points.

- **Python API**

    Substantive behavior should live in importable Python functions, classes, or service layers rather than only in Click callbacks.

- **Config and Environment**

    A released bounded `chatup>=0.2.3,<0.3.0` machine-environment dependency is declared. A ChatEnv provider scaffold exists; the production proposal separates non-secret TOML, secret profiles, runtime state, and the ledger.

- **Browser Runner Design**

    ChatUp owns Chrome installation. ChatPost designs host/Docker runners, multiple user-data-dirs, and bridge isolation; runner commands are not implemented.

- **Task-Oriented Zhihu Acceptance**

    The repository contains a fixed MkDocs article and local image. A future implementation uses one explicit draft create and never triggers final publish automatically.

</div>

## Current Boundary

| Capability | Status | Notes |
| --- | --- | --- |
| CLI base entry | Implemented | The template generates a Click group, `--version`, and a base test. |
| ChatEnv provider | Scaffold implemented | `config.py` and `chatenv.configs` exist, but `CHATPOST_API_KEY` is a placeholder and the production bridge schema is not implemented. |
| Overall architecture/config model | Proposed | The ChatUp dependency and Runner/Account/Publication, ChatEnv, and ledger boundaries are documented. |
| CLI structure design | Proposed | Runner/account/plan/draft/publication boundaries are documented; ChatPost no longer proposes browser-install commands. |
| ChatUp Chrome for Testing backend | Declared and verified | `pyproject.toml` bounds released `chatup 0.2.3`; tests verify the read-only public `chatup.chrome_for_testing.resolve` API. |
| Runner isolation | Proposed | Host binary by default and one user-data-dir/bridge per runner; ChatPost resolves a ChatUp descriptor and never installs Chrome. |
| Historical Zhihu draft path | Verified | The Wechatsync practice created and read back a draft using a direct binary, QR-scan login, dedicated profile, and loopback bridge; SMS remains separately unverified. |
| MkDocs Zhihu fixture | Added | `examples/zhihu/mkdocs-quickstart.md` and its PNG exist; no draft has been created through ChatPost commands yet. |
| Business commands | Not implemented | Add these from the real package domain; do not fake future commands in the template. |

## Out of Scope

- No plan placeholder page is generated.
- No unimplemented capability should be written as a user operation tutorial.
- Commands in design documents remain explicitly proposed until code, tests, and help text exist.
- The presence of the fixed article does not mean the ChatPost end-to-end path is implemented or that a new draft exists.
- No secret, token, cookie, or Authorization header should appear in README, docs, issues, PR comments, or CI logs.
