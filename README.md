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

[英文版](README.en.md) | [简体中文](README.md)
</div>

# ChatPost

ChatArch browser-level platform login foundation and draft entrypoint.

文档入口：<https://arch.gh.wzhecnu.cn/ChatPost/>

| 场景 | 文档 |
| --- | --- |
| 立即跑登录与草稿路径 | [Quickstart：浏览器登录与知乎草稿](docs/quickstart.md) |
| 查看当前真实命令 | [CLI 树](docs/cli-tree.md) |
| 校对当前能力和边界 | [能力地图](docs/capability-map.md) |
| Review Chrome/Profile 状态边界 | [配置、环境与状态](docs/configuration.md) |

## 快速开始

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
python -m pytest -q
python -m build
```

## 当前边界

`chatpost zhihu login/status/logout PROFILE` 是纯浏览器登录基础层：它只管理受控 Chromium Profile 和页面可见登录态，不调用发布适配器、不加载发布扩展、不要求发布 token、不读取或导出 Cookie/LocalStorage/IndexedDB/session/token。`chatpost zhihu draft PROFILE SOURCE` 是独立 Wechatsync adapter 入口：dry-run 使用 Wechatsync CLI parser 做预览；create 通过 Wechatsync extension MCP 直连创建一个草稿，不最终发布。

这个包依赖 `chatstyle>=0.1.1,<0.2.0`、`chatenv>=0.2.0,<0.3.0`、`chatup>=0.2.4,<0.3.0`、`chatbrowser>=0.1.2,<0.2.0`、`qrcode[pil]>=7.4,<9.0`、`websocket-client>=1.8,<2.0` 和 `websockets>=12.0,<16.0`。Playwright package/browser 安装由 ChatUp 负责；浏览器 runtime/Profile/CDP metadata 边界由 ChatBrowser 承担。
