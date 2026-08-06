# CLI 树

`ChatPost 0.1.x` 的命令面现在按“平台无关能力 + 平台专用能力”组织：顶层只保留账号 alias registry、通用 QR artifact 和具体平台名。登录、草稿和平台 runner 都挂到对应平台下；因此不再有全局 `chatpost login` 或 `chatpost post`。

## 当前真实命令

`chatpost --tree` 会打印真实注册 CLI 树、每个叶子的接口形状、用途和输出边界：

```text
chatpost  # platform content publishing and draft orchestration
├── --help  # Show help for the current command.
├── --version  # Show package version.
├── --tree  # Print the registered CLI tree with command purpose and IO shape.
├── account  # account alias registry; metadata only
│   ├── list [--registry PATH] [--output text|json] [-I/--no-interactive]  # List account aliases; never reads cookies/tokens/session.
│   └── show TARGET [--registry PATH] [--output text|json] [-I/--no-interactive]  # Show one account alias by ALIAS or PLATFORM@ALIAS.
├── qr  # platform-neutral QR artifact tools
│   └── encode DATA --artifact PATH [--output text|json] [-I/--no-interactive]  # Render DATA into PNG without echoing DATA by default.
└── zhihu  # Zhihu platform capabilities
    ├── account  # Zhihu account status, preflight, and login checkpoints
    │   ├── status TARGET [--registry PATH] [--output text|json] [-I/--no-interactive]  # Read-only Zhihu auth check.
    │   ├── preflight TARGET [--registry PATH] [--output text|json] [-I/--no-interactive]  # Check runner/profile/browser/extension readiness.
    │   └── login  # Zhihu manual login checkpoints; no phone/code/cookie arguments.
    │       ├── qr TARGET [--registry PATH] [--timeout INTEGER] [--output text|json] [-I/--no-interactive]  # Open QR login checkpoint and wait for READY.
    │       ├── qr-artifact TARGET [--registry PATH] --artifact PATH --receipt PATH [--timeout INTEGER] [--output text|json] [-I/--no-interactive]  # Create live QR PNG + receipt, return immediately.
    │       └── code TARGET [--registry PATH] [--timeout INTEGER] [--output text|json] [-I/--no-interactive]  # Open SMS-code checkpoint without accepting phone/code values.
    └── draft  # Zhihu review-draft operations
        ├── dry-run TARGET SOURCE [--registry PATH] [--output text|json] [-I/--no-interactive]  # Parse SOURCE without starting browser or writing Zhihu.
        └── create TARGET SOURCE [--registry PATH] --receipt PATH [--output text|json] [-I/--no-interactive]  # Create exactly one Zhihu review draft.
```

查看真实 help：

```bash
chatpost --tree
chatpost --help
chatpost account --help
chatpost qr --help
chatpost zhihu --help
chatpost zhihu account --help
chatpost zhihu account login --help
chatpost zhihu draft --help
```

## 常规任务顺序

准备一个只含非敏感 metadata 的账号 registry：

```toml
[accounts."zhihu-test"]
platform = "zhihu"
runner_config = "/absolute/path/to/runner.toml"
profile = "zhihu-test"
label = "Zhihu test account"
```

然后按平台作用域入口执行：

```bash
chatpost account list \
  --registry accounts.toml \
  --output json \
  -I

chatpost account show zhihu@zhihu-test \
  --registry accounts.toml \
  --output json \
  -I

chatpost qr encode 'https://www.zhihu.com/signin?login_method=qr' \
  --artifact login-url.png \
  --output json \
  -I

chatpost zhihu account status zhihu@zhihu-test \
  --registry accounts.toml \
  --output json \
  -I

chatpost zhihu account preflight zhihu@zhihu-test \
  --registry accounts.toml \
  --output json \
  -I

chatpost zhihu account login qr zhihu@zhihu-test \
  --registry accounts.toml \
  --timeout 900 \
  --output json \
  -I

chatpost zhihu account login qr-artifact zhihu@zhihu-test \
  --registry accounts.toml \
  --artifact live-login-qr.png \
  --receipt live-login-qr-ready.json \
  --timeout 60 \
  --output json \
  -I

chatpost zhihu account login code zhihu@zhihu-test \
  --registry accounts.toml \
  --timeout 900 \
  --output json \
  -I

chatpost zhihu draft dry-run zhihu@zhihu-test article.md \
  --registry accounts.toml \
  --output json \
  -I

chatpost zhihu draft create zhihu@zhihu-test article.md \
  --registry accounts.toml \
  --receipt receipt.json \
  --output json \
  -I
```

这些入口只是 ChatPost 编排层：

1. `account list/show` 只读账号 alias registry，不保存或回显 Cookie、LocalStorage、token、password、credential 等敏感值。
2. `qr encode` 把调用方提供的数据渲染为 PNG artifact，默认只报告 artifact metadata，不回显原始数据。
3. `zhihu account status` 解析 `platform@alias`，对知乎账号调用一次只读 auth check。
4. `zhihu account preflight` 检查 exact Playwright install、Profile 权限、扩展、Node、Wechatsync CLI、secret 文件和 loopback 端口；不会安装、启动或写知乎。
5. `zhihu account login qr` 打开二维码登录 checkpoint 并等待账号变为 `READY`；当前仍由浏览器/Profile 承载登录态，ChatPost 不导出 Cookie。
6. `zhihu account login qr-artifact` 打开 live 登录 checkpoint，在本轮 browser context 中创建新的知乎 scan-login 短链，把提取到的 `login_url` 渲染为 QR PNG，写 `0600` receipt，然后立刻返回；图片如何发送给用户由对话宿主/gateway 决定。
7. `zhihu account login code` 打开验证码登录 checkpoint 并等待 `READY`；手机号和验证码只在浏览器人工流程中使用，不作为 CLI 参数、不写 registry、config、receipt 或日志。
8. `zhihu draft dry-run` 只解析文章，不启动浏览器，不连接扩展，不写知乎。
9. `zhihu draft create` 只调用一次 Wechatsync create 路径。成功时写入权限 `0600` 的 receipt；结果不明确时写 `RESULT_UNKNOWN`，禁止自动重试。它创建 review 草稿，不是最终发布。

`ChatPost 0.1.x` **没有最终发布命令**，也没有文章更新命令。

## ChatUp / ChatBrowser 边界

机器级制品先由 ChatUp 显式准备：

```bash
chatup nodejs -I
chatup playwright install 1.61.1 --browser chromium --output json -I
chatup playwright doctor 1.61.1 --browser chromium --output json -I
```

ChatPost 依赖 `chatup>=0.2.4,<0.3.0`、`chatbrowser>=0.1.2,<0.2.0` 和 `qrcode[pil]>=7.4,<9.0`。当前知乎写草稿路径仍直接通过 ChatUp resolve exact browser，再由 ChatPost 管理 Profile、扩展、loopback CDP/bridge、QR/link handoff artifact 与 Wechatsync 进程；账号 registry 只保存非敏感 alias metadata。ChatBrowser 负责浏览器 runtime/profile/session metadata 的安全边界，后续更丰富的 session 发现应从 ChatBrowser 接入，而不是在 ChatPost 里保存浏览器秘密。

```python
from chatup.playwright import resolve

installation = resolve("1.61.1", browser="chromium")
```

责任边界：

- ChatUp：Playwright package、它声明的 browser revision、安装元数据和 executable path；
- ChatBrowser：浏览器 runtime、Profile metadata、CDP session metadata；
- ChatPost：账号 alias、QR 图片 artifact、发布任务编排、Profile/扩展/CDP/bridge/Wechatsync 单次任务与 receipt；
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
attach_existing_cdp = false
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
publication list|show|retry
article update
post publish
```

实现这些命令前，文档必须持续标为提案；不得把它们写进可执行 Quick Start。
