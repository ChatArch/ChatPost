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

ChatArch browser-level platform login foundation and draft entrypoint.

Docs: <https://arch.gh.wzhecnu.cn/ChatPost/>

| Scenario | Document |
| --- | --- |
| Run login and draft flows now | [Quickstart: Browser Login, Zhihu Drafts, and Xiaohongshu Login](docs/quickstart.en.md) |
| Inspect the real CLI tree | [CLI Tree](docs/cli-tree.en.md) |
| Check current capabilities and boundaries | [Capability Map](docs/capability-map.md) |
| Review Chrome/Profile state boundaries | [Configuration, Environment, and State](docs/configuration.en.md) |

## Quick Start

```bash
pip install -e ".[dev]"
chatpost --help
chatpost --version
chatpost --tree
chatpost platforms --help
chatpost profiles --help
chatpost zhihu --help
chatpost zhihu profiles --help
chatpost zhihu login --help
chatpost zhihu status --help
chatpost zhihu logout --help
chatpost zhihu draft --help
chatpost xiaohongshu --help
chatpost xiaohongshu profiles --help
chatpost xiaohongshu login --help
chatpost xiaohongshu status --help
chatpost xiaohongshu logout --help
chatpost xiaohongshu draft --help
python -m pytest -q
python -m build
```

## Current Boundary

`chatpost zhihu login/status/logout PROFILE` and `chatpost xiaohongshu login/status/logout PROFILE` are pure browser login foundation commands: they manage only the controlled Chromium Profile and page-visible login state. They do not call a publishing adapter, load a publishing extension, require a publishing token, or read/export cookies/local storage/IndexedDB/sessions/tokens. `chatpost zhihu draft PROFILE SOURCE` is a separate Wechatsync adapter entrypoint: dry-run uses the Wechatsync CLI parser for preview, while create talks directly to the Wechatsync extension MCP bridge to create one draft and never final-publishes. `chatpost xiaohongshu draft PROFILE SOURCE` currently performs local dry-run/source validation only; create explicitly returns `CREATE_NOT_SUPPORTED` until a Xiaohongshu adapter is connected.

This package depends on `chatstyle>=0.1.1,<0.2.0`, `chatenv>=0.2.0,<0.3.0`, `chatup>=0.2.4,<0.3.0`, `chatbrowser>=0.1.2,<0.2.0`, `qrcode[pil]>=7.4,<9.0`, `websocket-client>=1.8,<2.0`, and `websockets>=12.0,<16.0`. ChatUp owns Playwright package/browser installation. ChatBrowser owns the browser runtime, Profile metadata, and CDP metadata safety boundary.
