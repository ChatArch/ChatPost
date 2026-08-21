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
| Run Zhihu/CSDN login and draft flows now | [Quickstart: Logical Profiles, Zhihu/CSDN Login, and Drafts](docs/quickstart.en.md) |
| Inspect the real CLI tree | [CLI Tree](docs/cli-tree.en.md) |
| Check current capabilities and boundaries | [Capability Map](docs/capability-map.md) |
| Review Chrome/Profile state boundaries | [Configuration, Environment, and State](docs/configuration.en.md) |

## Quick Start

```bash
pip install ChatPost
chatpost --version
chatup playwright install 1.61.1 --browser chromium --output json -I
chatbrowser profile create zhihu-test \
  --path "$HOME/.chatarch/chatpost/profiles/test/zhihu" \
  --backend chatup-playwright \
  --label owner=chatpost \
  --label platform=zhihu \
  --label logical_profile=test \
  --output json
```

Repository development setup:

```bash
pip install -e ".[dev]"
chatpost --help
chatpost --version
chatpost --tree
chatpost --tree-brief
chatpost platforms --help
chatpost profiles --help
chatpost zhihu --help
chatpost zhihu profiles --help
chatpost zhihu login --help
chatpost zhihu status --help
chatpost zhihu logout --help
chatpost zhihu draft --help
chatpost xhs --help
chatpost xhs profiles --help
chatpost xhs login --help
chatpost xhs status --help
chatpost xhs logout --help
chatpost csdn --help
chatpost csdn profiles --help
chatpost csdn login --help
chatpost csdn status --help
chatpost csdn logout --help
chatpost csdn draft --help
python -m pytest -q
python -m build
```

## Current Boundary

`chatpost zhihu/xhs/csdn login/status/logout PROFILE` commands are the pure browser login foundation: they manage only the controlled Chromium Profile and page-visible login state. They do not call a publishing adapter, load a publishing extension, require a publishing token, or read/export cookies/local storage/IndexedDB/sessions/tokens. Zhihu may emit a page-owned `login_url` when logged out; XHS and CSDN are QR-image-only when logged out: `chatpost xhs login PROFILE --qrcode PATH` / `chatpost csdn login PROFILE --qrcode PATH` write a mode-`0600` QR artifact, and user-visible output contains only `qrcode_path`, never `login_url`, `loginconfirm`, raw data URLs, base64, or QR tokens. `chatpost zhihu draft PROFILE SOURCE` and `chatpost csdn draft PROFILE SOURCE` are separate Wechatsync adapter entrypoints: dry-run uses the Wechatsync CLI parser for preview, while create talks directly to the Wechatsync extension MCP bridge to create one draft and never final-publishes. The current Wechatsync CSDN adapter returns `draftOnly=true`, so ChatPost has no CSDN public `post/publish` command. XHS draft/publish is not in the current user-visible CLI surface.

This package depends on `chatstyle>=0.2.0,<0.3.0`, `chatenv>=0.2.10,<0.3.0`, `chatup>=0.2.12,<0.3.0`, `chatbrowser>=0.1.5,<0.2.0`, `qrcode[pil]>=7.4,<9.0`, `websocket-client>=1.8,<2.0`, and `websockets>=12.0,<16.0`. ChatStyle renders `chatpost --tree` (with signatures) and `chatpost --tree-brief` (without signatures) from the real Click registry. ChatUp owns Playwright package/browser installation. ChatBrowser owns the browser runtime, Profile metadata, and CDP metadata safety boundary. A ChatPost runner may reference a ChatBrowser Profile with `browser_profile = "zhihu-test"` / `browser_profile = "csdn-test"`, while Wechatsync extension/bridge/receipt details stay in the ChatPost adapter layer.
