<div align="center">
    <a href="https://pypi.python.org/pypi/ChatPost">
        <img src="https://img.shields.io/pypi/v/ChatPost.svg" alt="PyPI version" />
    </a>
    <a href="https://github.com/ChatArch/ChatPost/actions/workflows/ci.yml">
        <img src="https://github.com/ChatArch/ChatPost/actions/workflows/ci.yml/badge.svg" alt="Tests" />
    </a>
    <a href="https://arch.gh.wzhecnu.cn/ChatPost/">
        <img src="https://img.shields.io/badge/docs-mkdocs-blue.svg" alt="Documentation" />
    </a>
</div>

<div align="center">

[English](README.en.md) | [简体中文](README.md)
</div>

# ChatPost

ChatArch multi-platform content publishing infrastructure package.


Documentation entry: <https://arch.gh.wzhecnu.cn/ChatPost/en/>

Choose documentation by scenario:

| Scenario | Document |
| --- | --- |
| Understand ChatPost resources and data flow | [Overall Architecture](docs/architecture.en.md) |
| Review the ChatUp Chrome dependency, ChatEnv, and state ownership | [Configuration, Environment, and State](docs/configuration.en.md) |
| Follow first Zhihu login and fixed-article draft acceptance | [Zhihu First Setup and Draft Acceptance](docs/zhihu-first-run.en.md) |
| Run the fastest Playwright + Wechatsync Zhihu draft path | [Zhihu First Setup and Draft Acceptance](docs/zhihu-first-run.en.md) |
| Inspect the current real commands | [CLI Tree](docs/cli-tree.en.md) |
| Review the proposed CLI, ChatUp runtime dependency, and multi-account isolation | [Browser Runners and Account Isolation](docs/browser-runners.en.md) |
| Check first-class capabilities and current boundaries | [Capability Map](docs/capability-map.en.md) |
| Call package behavior directly from Python | [Python Interface Tree](docs/interface-tree.md) |

## Quick Start

```bash
pip install -e ".[dev]"
chatpost --help
chatpost --version
chatpost zhihu --help
python -m pytest -q
python -m build
```

## CLI Contract

This package depends on `chatstyle>=0.1.1,<0.2.0`, `chatenv>=0.2.0,<0.3.0`, `chatup>=0.2.4,<0.3.0`, and `websocket-client>=1.8,<2.0`. ChatUp owns Playwright package/browser installation. ChatPost only resolves an exact descriptor and owns the Profile, extension, loopback CDP/bridge, and one-shot draft task.

- `CommandSchema` / `CommandField` for inputs.
- `add_interactive_option()` for the shared `-i/-I` switch.
- `resolve_command_inputs()` for missing args, defaults, TTY behavior, and validation.
- Generate `config.py` and a `chatenv.configs` entry point by default so the package is ChatEnv-discoverable; use `--without-chatenv-provider` only when ChatEnv integration is intentionally not needed.

## Layout

- `src/`: package source code
- `tests/code-tests/`: code tests and migrated historical tests
- `tests/cli-tests/`: real CLI tests, doc-first
- `tests/mock-cli-tests/`: mock/fake CLI tests, doc-first
- `docs/`: long-lived project docs built by mkdocs

## Development Notes

See `DEVELOP.md` and `AGENTS.md` before expanding the scaffold.
