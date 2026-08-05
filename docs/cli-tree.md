# CLI 树

`ChatPost 0.1.x` 现在提供两层入口：面向日常使用的通用任务入口，以及保留给低层诊断/兼容的 `zhihu` 专用入口。正式发布仍未实现；当前可验证写入是“创建知乎 review 草稿”。

## 当前真实命令

```text
chatpost
├── --help
├── --version
├── account                         # 非敏感账号 alias registry
│   ├── list                         # 查看已有账号 alias
│   └── show                         # 查看一个账号 alias
├── login                           # 登录状态与人工登录 checkpoint
│   ├── status                       # read-only auth check
│   ├── qr                           # 打开登录页/二维码 checkpoint 并等待 READY
│   └── code                         # 打开验证码登录 checkpoint 并等待 READY；不接收手机号/验证码参数
├── post                            # 发 Post 的 review-draft 入口
│   └── draft                        # 创建一个平台 review 草稿；不是最终发布
└── zhihu                           # 低层知乎 runner 兼容入口
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
chatpost account --help
chatpost login --help
chatpost post --help
chatpost zhihu --help
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

然后按常规入口执行：

```bash
chatpost account list \
  --registry accounts.toml \
  --output json \
  -I

chatpost account show zhihu@zhihu-test \
  --registry accounts.toml \
  --output json \
  -I

chatpost login status zhihu@zhihu-test \
  --registry accounts.toml \
  --output json \
  -I

chatpost login qr zhihu@zhihu-test \
  --registry accounts.toml \
  --timeout 900 \
  --output json \
  -I

chatpost login code zhihu@zhihu-test \
  --registry accounts.toml \
  --timeout 900 \
  --output json \
  -I

chatpost post draft zhihu@zhihu-test article.md \
  --registry accounts.toml \
  --receipt receipt.json \
  --output json \
  -I
```

这些常规入口只是 ChatPost 编排层：

1. `account list/show` 只读账号 alias registry，不保存或回显 Cookie、LocalStorage、token、password、credential 等敏感值。
2. `login status` 解析 `platform@alias`，对知乎账号调用一次只读 auth check。
3. `login qr` 打开二维码登录 checkpoint 并等待账号变为 `READY`；当前仍由浏览器/Profile 承载登录态，ChatPost 不导出 Cookie。
4. `login code` 打开验证码登录 checkpoint 并等待 `READY`；手机号和验证码只在浏览器人工流程中使用，不作为 CLI 参数、不写 registry、config、receipt 或日志。
5. `post draft` 只创建一个 review 草稿并写 `0600` receipt。它是“发 Post”的当前安全验收入口，不是最终发布。

## 低层知乎 runner 入口

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

五道低层门的职责不同：

1. `preflight` 只读检查 exact Playwright install、Profile 权限、扩展、Node、Wechatsync CLI、secret 文件和 loopback 端口；不会安装、启动或写知乎。
2. `login` 保持同一个浏览器/Profile，打开知乎登录页并循环只读 auth；适合扫码或验证码的人工 checkpoint，不写文章。常规入口中 `login code` 只是选择验证码 checkpoint，不保存手机号或验证码。
3. `auth` 启动同一个 Runner，调用 Wechatsync 的一次只读知乎登录检查，然后优雅停止浏览器。
4. `draft dry-run` 只解析文章，不启动浏览器，不连接扩展，不写知乎。
5. `draft create` 只调用一次 Wechatsync create 路径。成功时写入权限 `0600` 的 receipt；结果不明确时写 `RESULT_UNKNOWN`，禁止自动重试。

`ChatPost 0.1.x` **没有最终发布命令**，也没有文章更新命令。

## ChatUp / ChatBrowser 边界

机器级制品先由 ChatUp 显式准备：

```bash
chatup nodejs -I
chatup playwright install 1.61.1 --browser chromium --output json -I
chatup playwright doctor 1.61.1 --browser chromium --output json -I
```

ChatPost 依赖 `chatup>=0.2.4,<0.3.0` 和 `chatbrowser>=0.1.2,<0.2.0`。当前知乎写草稿路径仍直接通过 ChatUp resolve exact browser，再由 ChatPost 管理 Profile、扩展、loopback CDP/bridge 与 Wechatsync 进程；账号 registry 只保存非敏感 alias metadata。ChatBrowser 负责浏览器 runtime/profile/session metadata 的安全边界，后续更丰富的 session 发现应从 ChatBrowser 接入，而不是在 ChatPost 里保存浏览器秘密。

```python
from chatup.playwright import resolve

installation = resolve("1.61.1", browser="chromium")
```

责任边界：

- ChatUp：Playwright package、它声明的 browser revision、安装元数据和 executable path；
- ChatBrowser：浏览器 runtime、Profile metadata、CDP session metadata；
- ChatPost：账号 alias、发布任务编排、Profile/扩展/CDP/bridge/Wechatsync 单次任务与 receipt；
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
