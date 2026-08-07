# CLI 树

`ChatPost 0.1.x` 的用户可见命令面按“发现入口 + 平台专用能力”组织。顶层只暴露平台发现、Profile 发现和具体平台名；知乎登录、登出、状态和草稿都挂在 `chatpost zhihu ...` 下，因此不再有全局 `chatpost login` 或 `chatpost post`。

这里的 `profile` 指一个非敏感的 Chrome/Profile target 配置：它把 alias、platform、runner_config、profile 名和 label 绑定起来，方便 `login/status/logout/draft` 找到对应浏览器 Profile；它不是 Cookie、LocalStorage、知乎账号详情或凭据。

## 当前真实命令

`chatpost --tree` 会打印真实注册 CLI 树、每个叶子的接口形状、用途和输出边界：

```text
chatpost  # platform content publishing and draft orchestration
├── --help  # Show help for the current command.
├── --version  # Show package version.
├── --tree  # Print the registered CLI tree with command purpose and IO shape.
├── platforms [--output text|json] [-I/--no-interactive]  # List supported publishing platforms.
├── profiles [--platform zhihu] [--registry PATH] [--output text|json] [-I/--no-interactive]  # List configured Chrome/profile targets.
└── zhihu  # Zhihu platform capabilities
    ├── profiles [--registry PATH] [--output text|json] [-I/--no-interactive]  # List configured Zhihu Chrome/profile targets.
    ├── login PROFILE [--registry PATH] [--qr PATH] [--receipt PATH] [--timeout INTEGER] [--output text|json] [-I/--no-interactive]  # Open live QR login, emit link/QR/receipt, and wait for READY.
    ├── logout PROFILE [--registry PATH] [--output text|json] [-I/--no-interactive]  # Clear Zhihu login state for this profile; does not read session values.
    ├── status PROFILE [--registry PATH] [--output text|json] [-I/--no-interactive]  # Read-only Zhihu auth check.
    └── draft  # Zhihu review-draft operations
        ├── dry-run PROFILE SOURCE [--registry PATH] [--output text|json] [-I/--no-interactive]  # Parse SOURCE without starting browser or writing Zhihu.
        └── create PROFILE SOURCE [--registry PATH] --receipt PATH [--output text|json] [-I/--no-interactive]  # Create exactly one Zhihu review draft.
```

查看真实 help：

```bash
chatpost --tree
chatpost --help
chatpost platforms --help
chatpost profiles --help
chatpost zhihu --help
chatpost zhihu profiles --help
chatpost zhihu login --help
chatpost zhihu logout --help
chatpost zhihu status --help
chatpost zhihu draft --help
```

## 常规任务顺序

准备一个只含非敏感 metadata 的 Profile registry：

```toml
[accounts."zhihu-test"]
platform = "zhihu"
runner_config = "/absolute/path/to/runner.toml"
profile = "zhihu-test"
label = "Zhihu test account"
```

然后执行可见平台入口：

```bash
chatpost platforms \
  --output json \
  -I

chatpost zhihu profiles \
  --registry accounts.toml \
  --output json \
  -I

chatpost zhihu login zhihu-test \
  --registry accounts.toml \
  --qr live-login-qr.png \
  --receipt live-login-qr-ready.json \
  --timeout 900 \
  --output json \
  -I

chatpost zhihu status zhihu-test \
  --registry accounts.toml \
  --output json \
  -I

chatpost zhihu logout zhihu-test \
  --registry accounts.toml \
  --output json \
  -I

chatpost zhihu draft dry-run zhihu-test article.md \
  --registry accounts.toml \
  --output json \
  -I

chatpost zhihu draft create zhihu-test article.md \
  --registry accounts.toml \
  --receipt receipt.json \
  --output json \
  -I
```

这些入口只是 ChatPost 编排层：

1. `platforms` 列出当前一等平台和推荐入口。
2. `profiles` / `zhihu profiles` 只读 Profile registry，不保存或回显 Cookie、LocalStorage、token、password、credential 等敏感值。
3. `zhihu login` 是一个二维码登录 handoff：打开同一个浏览器 Profile 的知乎登录页，等待页面二维码可扫，使用**同一个登录页正在轮询的 page-owned `login_url`** 生成 QR 图片/写 `0600` receipt，然后保持浏览器打开并等待账号变为 `READY`。当前仍由浏览器/Profile 承载登录态，ChatPost 不导出 Cookie。
4. `zhihu status` 解析 `PROFILE`，对知乎 Profile 调用一次只读 auth check，不读 Cookie、LocalStorage 或 IndexedDB。
5. `zhihu logout` 清理该 Profile 下知乎 origin 的登录态；它只发浏览器存储清理命令，不读取或导出 session 值。
6. `zhihu draft dry-run` 只解析文章，不启动浏览器，不连接扩展，不写知乎。
7. `zhihu draft create` 只调用一次 Wechatsync create 路径。成功时写入权限 `0600` 的 receipt；结果不明确时写 `RESULT_UNKNOWN`，禁止自动重试。它创建 review 草稿，不是最终发布。
8. 手机号和验证码只属于人工浏览器流程；ChatPost 不提供 `--phone`、`--code`、`--otp` 或 `--sms-code` 参数，也不会把这些值写入 registry、config、receipt 或日志。

`ChatPost 0.1.x` **没有最终发布命令**，也没有文章更新命令。

## Hidden compatibility

旧的脚本入口仍可调用，但不出现在 `--help` 或 `--tree` 中：

```text
chatpost account list/show
chatpost qr encode
chatpost zhihu account status/preflight/login qr/login qr-artifact/login code
```

这些 hidden compatibility 命令用于兼容既有自动化，不是新的日常文档路径；平台发送图片仍由宿主/gateway 决定，ChatPost CLI 不输出 `MEDIA:ssh://...` 或 `[media attachment]`。

## ChatUp / ChatBrowser 边界

机器级制品先由 ChatUp 显式准备：

```bash
chatup nodejs -I
chatup playwright install 1.61.1 --browser chromium --output json -I
chatup playwright doctor 1.61.1 --browser chromium --output json -I
```

ChatPost 依赖 `chatup>=0.2.4,<0.3.0`、`chatbrowser>=0.1.2,<0.2.0` 和 `qrcode[pil]>=7.4,<9.0`。当前知乎写草稿路径仍直接通过 ChatUp resolve exact browser，再由 ChatPost 管理 Profile、扩展、loopback CDP/bridge、QR/link handoff artifact 与 Wechatsync 进程；Profile registry 只保存非敏感 alias metadata。ChatBrowser 负责浏览器 runtime/profile/session metadata 的安全边界，后续更丰富的 session 发现应从 ChatBrowser 接入，而不是在 ChatPost 里保存浏览器秘密。

```python
from chatup.playwright import resolve

installation = resolve("1.61.1", browser="chromium")
```

责任边界：

- ChatUp：Playwright package、它声明的 browser revision、安装元数据和 executable path；
- ChatBrowser：浏览器 runtime、Profile metadata、CDP session metadata；
- ChatPost：Profile alias、QR 图片 artifact、发布任务编排、Profile/扩展/CDP/bridge/Wechatsync 单次任务与 receipt；
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
