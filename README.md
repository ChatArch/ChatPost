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

ChatArch multi-platform content publishing infrastructure package.


文档入口：<https://arch.gh.wzhecnu.cn/ChatPost/>

按场景选择文档：

| 场景 | 文档 |
| --- | --- |
| 理解 ChatPost 总体资源和数据流 | [总体架构](docs/architecture.md) |
| Review ChatUp Chrome dependency、ChatEnv 与状态边界 | [配置、环境与状态](docs/configuration.md) |
| 查看知乎首次登录和固定博客草稿验收 | [知乎首次设置与草稿验收](docs/zhihu-first-run.md) |
| 最快打通 Playwright + Wechatsync 知乎草稿 | [知乎首次设置与草稿验收](docs/zhihu-first-run.md) |
| 查看当前真实命令 | [CLI 树](docs/cli-tree.md) |
| Review 预期 CLI、ChatUp runtime dependency 与多账号隔离 | [Browser Runner 与账号隔离](docs/browser-runners.md) |
| 校对当前包有哪些一等能力和边界 | [能力地图](docs/capability-map.md) |
| 从 Python 代码调用包能力 | [接口树](docs/interface-tree.md) |

## 快速开始

```bash
pip install -e ".[dev]"
chatpost --help
chatpost --version
chatpost --tree
chatpost account --help
chatpost qr --help
chatpost zhihu --help
chatpost zhihu account login --help
chatpost zhihu draft --help
python -m pytest -q
python -m build
```

## 命令行规范

这个包依赖 `chatstyle>=0.1.1,<0.2.0`、`chatenv>=0.2.0,<0.3.0`、`chatup>=0.2.4,<0.3.0`、`chatbrowser>=0.1.2,<0.2.0`、`qrcode[pil]>=7.4,<9.0` 和 `websocket-client>=1.8,<2.0`。Playwright package/browser 安装由 ChatUp 负责；浏览器 runtime/Profile/CDP metadata 边界由 ChatBrowser 承担；ChatPost 只解析 exact descriptor、账号 alias、QR 图片 artifact 和发布任务，并管理 Profile、扩展、loopback CDP/bridge 与单次 review 草稿任务。

- `CommandSchema` / `CommandField` 描述输入。
- `add_interactive_option()` 提供统一 `-i/-I`。
- `resolve_command_inputs()` 统一缺参补问、默认值、TTY 与校验。
- 默认生成 `config.py` 和 `chatenv.configs` 入口点，使包可被 ChatEnv 发现；只有明确不需要 ChatEnv 接入时才使用 `--without-chatenv-provider`。

## 目录结构

- `src/`：包源码
- `tests/code-tests/`：代码测试和历史测试迁移
- `tests/cli-tests/`：真实 CLI 测试，doc-first
- `tests/mock-cli-tests/`：mock/fake CLI 测试，doc-first
- `docs/`：长期维护文档，由 mkdocs 构建

## 开发说明

扩展脚手架前，先阅读 `DEVELOP.md` 和 `AGENTS.md`。
