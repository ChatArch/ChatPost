# CLI 树

`ChatPost 0.1.0` 首先提供一条任务导向的知乎草稿链路。通用 `runner`、`account`、`publication` 和文章更新命令仍是后续设计，不能当作当前接口。

## 当前真实命令

```text
chatpost
├── --help
├── --version
└── zhihu
    ├── preflight
    ├── login
    ├── auth
    └── draft
        ├── dry-run
        └── create
```

查看真实 help：

```bash
chatpost --help
chatpost zhihu --help
chatpost zhihu draft --help
```

## 任务顺序

```bash
chatpost zhihu preflight \
  --config runner.toml \
  --output json \
  -I

chatpost zhihu login \
  --config runner.toml \
  --timeout 900 \
  --output json \
  -I

chatpost zhihu auth \
  --config runner.toml \
  --output json \
  -I

chatpost zhihu draft dry-run article.md \
  --config runner.toml \
  --output json \
  -I

chatpost zhihu draft create article.md \
  --config runner.toml \
  --receipt receipt.json \
  --output json \
  -I
```

五道门的职责不同：

1. `preflight` 只读检查 exact Playwright install、Profile 权限、扩展、Node、Wechatsync CLI、secret 文件和 loopback 端口；不会安装、启动或写知乎。
2. `login` 保持同一个浏览器/Profile，打开知乎登录页并循环只读 auth；适合扫码或验证码的人工 checkpoint，不写文章。
3. `auth` 启动同一个 Runner，调用 Wechatsync 的一次只读知乎登录检查，然后优雅停止浏览器。
4. `draft dry-run` 只解析文章，不启动浏览器，不连接扩展，不写知乎。
5. `draft create` 只调用一次 Wechatsync create 路径。成功时写入权限 `0600` 的 receipt；结果不明确时写 `RESULT_UNKNOWN`，禁止自动重试。

`ChatPost 0.1.0` **没有最终发布命令**，也没有文章更新命令。

## ChatUp 边界

机器级制品先由 ChatUp 显式准备：

```bash
chatup nodejs -I
chatup playwright install 1.61.1 --browser chromium --output json -I
chatup playwright doctor 1.61.1 --browser chromium --output json -I
```

ChatPost 依赖 `chatup>=0.2.4,<0.3.0`，并只调用：

```python
from chatup.playwright import resolve

installation = resolve("1.61.1", browser="chromium")
```

责任边界：

- ChatUp：Playwright package、它声明的 browser revision、安装元数据和 executable path；
- ChatPost：持久 Profile、扩展、CDP、loopback bridge、Wechatsync 进程、单次任务与 receipt；
- Wechatsync：知乎 adapter 与草稿写入；
- 人工：首次登录和最终发布确认。

这里的 Playwright 能力是**安装和解析 substrate**。当前成功路径仍直接启动浏览器二进制，并通过原始 CDP 唤醒扩展；没有使用 Playwright `Page`、Locator 或 `launchPersistentContext()`。

## 非秘密 Runner 配置

```toml
[zhihu]
playwright_version = "1.61.1"
playwright_home = "/absolute/path/to/.chatarch/playwright"
profile_dir = "/absolute/path/to/zhihu-profile"
extension_dir = "/absolute/path/to/Wechatsync/packages/extension/dist"
node_bin = "/absolute/path/to/node"
wechatsync_cli = "/absolute/path/to/Wechatsync/packages/cli/dist/index.js"
env_file = "/absolute/path/to/chatpost-zhihu.env"
cdp_host = "127.0.0.1"
cdp_port = 9227
bridge_host = "127.0.0.1"
bridge_port = 9527
extension_id = "dipgimoobbhdefncjomgehikkbaklgii"
headless = true
browser_args = ["--disable-dev-shm-usage"]
```

安全约束：

- `profile_dir` 必须存在且不得向 group/other 开放；
- `env_file` 必须是 `0600` 或更严格，并包含 `WECHATSYNC_TOKEN`；
- CDP 与 bridge 只能绑定 loopback；
- `browser_args` 不能覆盖 Profile、CDP 或扩展所有权参数；
- 配置文件只保存路径和非秘密值，不保存 Cookie、LocalStorage 或知乎凭据。

## 仍属提案的命令

以下资源边界仍有价值，但命令尚未实现：

```text
runner add|start|status|doctor|stop
account add|login|status
publication list|show|retry
article update
```

实现这些命令前，文档必须持续标为提案；不得把它们写进可执行 Quick Start。
