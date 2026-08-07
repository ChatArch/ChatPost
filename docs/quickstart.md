# Quickstart：纯浏览器登录

本页只覆盖 ChatPost 的登录基础层：发现 Profile、检查知乎网页登录态、打开登录 handoff、以及登出/清理。它不创建草稿、不发布内容、不调用发布适配器，也不会读取或导出 Cookie、LocalStorage、IndexedDB、session 或 token 原值。

## 0. 设定变量

```bash
CHATPOST=chatpost
CHATPOST_HOME="${CHATPOST_HOME:-$HOME/.chatarch/chatpost}"
REGISTRY="${CHATPOST_ACCOUNT_REGISTRY:-$CHATPOST_HOME/accounts.toml}"
PROFILE=zhihu-personal
```

ChatPost 默认把本地状态放在 ChatArch 内部目录 `~/.chatarch/chatpost/`：默认 registry 是 `~/.chatarch/chatpost/accounts.toml`，runner/Profile/receipt 等后续状态也应放在这个 state root 下。`--registry` 只用于显式覆盖或任务级实验；不要把默认 `accounts.toml` 放到仓库根目录、当前工作目录或临时 project 目录。

`accounts.toml` 只保存非敏感 Profile metadata，例如 alias、platform、runner_config、profile 和 label。不要把 Cookie、LocalStorage、二维码 payload、验证码、手机号、密码、token 或 WebSocket UUID 写入 registry、config、日志或文档。相对 `runner_config` 路径按 registry 所在目录解析，因此默认情况下也会落在 `~/.chatarch/chatpost/` 内部。

## 1. 确认可见 CLI 和 Profile

```bash
"$CHATPOST" --tree

"$CHATPOST" platforms   --output json   -I

"$CHATPOST" profiles   --platform zhihu   --registry "$REGISTRY"   --output json   -I

"$CHATPOST" zhihu profiles   --registry "$REGISTRY"   --output json   -I
```

这些发现命令只读 registry，不启动浏览器，不读取登录态。等价真实命令名是 `chatpost platforms`、`chatpost profiles` 和 `chatpost zhihu profiles`。

登录基础层的真实命令名是 `chatpost zhihu status`、`chatpost zhihu login` 和 `chatpost zhihu logout`。

## 2. 检查当前网页登录态

```bash
"$CHATPOST" zhihu status "$PROFILE"   --registry "$REGISTRY"   --output json   -I
```

`status` 只做 browser-level 页面检查：打开/连接受控 Chromium Profile，通过知乎页面的 URL、DOM、可见账号入口判断状态。输出状态为：

- `LOGGED_IN`：页面可见信息能确认已登录，可带 `account_name` / `account_url`；
- `LOGGED_OUT`：页面可见信息显示未登录；
- `UNKNOWN`：页面无法可靠判断，且不会 fallback 到发布适配器。

## 3. 登录或复用已登录 Profile

```bash
"$CHATPOST" zhihu login "$PROFILE"   --registry "$REGISTRY"   --timeout 900   --output json   -I
```

行为约定：

- 已登录：先做 browser-page status，确认已登录后直接返回 `LOGGED_IN`，不会发 QR、不会发登录链接；
- 未登录：打开同一个 Profile 的知乎登录页，尽快输出 page-owned `login_url` 或 `browser_opened` handoff，然后保持浏览器等待人工完成登录；
- 不读取或导出 Cookie、LocalStorage、IndexedDB、session、token；
- 不调用发布适配器，不需要 adapter env，不需要发布 token；
- 页面截图不是登录 handoff，不能冒充最终登录交付；
- 机器验证、滑块、手机号和验证码都属于人工浏览器流程，CLI 不提供 `--phone`、`--code`、`--otp` 或 `--sms-code`。

JSON 输出是 JSON Lines：先输出可交互 handoff 事件，最后输出登录完成或超时事件。

## 4. 回读状态验收

```bash
"$CHATPOST" zhihu status "$PROFILE"   --registry "$REGISTRY"   --output json   -I
```

登录实践完成后，应看到 `LOGGED_IN`，并尽可能看到页面可见的 `account_name` 或 `account_url`。

## 5. 登出/清理

```bash
"$CHATPOST" zhihu logout "$PROFILE"   --registry "$REGISTRY"   --output json   -I
```

`logout` 先做 browser-level status：未登录时返回 `ALREADY_LOGGED_OUT`；已登录时才清理知乎 origins 登录态。清理是浏览器命令，不读取任何 session 原值。

## 常见停点

| 停点 | 处理 |
| --- | --- |
| `login` 直接返回 `LOGGED_IN` | 预期行为，说明 Profile 已登录。 |
| `login` 输出 `browser_opened` 但没有 page-owned `login_url` | 浏览器已打开等待人工登录；不要用截图或私有 artifact 冒充登录链接。 |
| 登录页需要滑块或验证码 | 停在人工浏览器流程，不把验证码写进 CLI 参数或日志。 |
| `status` 返回 `UNKNOWN` | 只报告未知；不要 fallback 到发布适配器或读取 Cookie/token。 |

## 附录：真实 CLI 运行记录（2026-08-08）

以下 transcript 来自 `/home/zhihong/Playground/core/ChatPost`，环境为 `PATH=/home/zhihong/.chatarch/venv/bin:$PATH` 与 `PYTHONPATH=src`。`logout` 未运行；其余当前登录基础层接口均实际执行。

旧 registry：`/home/zhihong/Playground/projects/chatarch/08-05-chatpost-login-cli-practice/playground/accounts.toml`。

Practice registry：`/home/zhihong/Playground/projects/chatarch/08-05-chatpost-login-cli-practice/playground/quickstart-practice-20260807-182534/accounts.toml`。

说明：以下 transcript 基于真实 CLI 运行；一次性 live `login_url`、账号展示名和账号主页 URL 在公开文档中脱敏或省略，其他字段保留真实命令结果。

### root_help

```bash
$ chatpost --help
exit: 0
stdout:
Usage: chatpost [OPTIONS] [COMMAND] [ARGS]...

  ChatPost browser-login command line interface.

Options:
  --version  Show the version and exit.
  --tree     Print the registered CLI tree.
  --help     Show this message and exit.

Commands:
  platforms  List supported platforms.
  profiles   List configured browser Profiles without reading login state.
  zhihu      Run pure browser-level Zhihu login/status/logout operations.
```

### root_version

```bash
$ chatpost --version
exit: 0
stdout:
chatpost, version 0.1.0
```

### root_tree

```bash
$ chatpost --tree
exit: 0
stdout:
chatpost  # browser-level platform login manager
├── --help  # Show help for the current command.
├── --version  # Show package version.
├── --tree  # Print the registered CLI tree with command purpose and IO shape.
├── platforms [--output text|json] [-I/--no-interactive]  # List supported platforms without starting a browser.
├── profiles [--platform zhihu] [--registry PATH] [--output text|json] [-I/--no-interactive]  # List configured browser Profiles without checking login state.
└── zhihu  # Zhihu browser login capabilities
    ├── profiles [--registry PATH] [--output text|json] [-I/--no-interactive]  # List configured Zhihu browser Profiles.
    ├── login PROFILE [--registry PATH] [--timeout INTEGER] [--output text|json] [-I/--no-interactive]  # Open/check a pure browser login session; emit page-owned login_url if needed.
    ├── status PROFILE [--registry PATH] [--output text|json] [-I/--no-interactive]  # Check Zhihu web login state from page-visible browser state only.
    └── logout PROFILE [--registry PATH] [--output text|json] [-I/--no-interactive]  # Log out or clear Zhihu browser state after browser-level status.
```

### platforms

```bash
$ chatpost platforms --output json -I
exit: 0
stdout:
{
  "platforms": [
    {
      "login_command": "chatpost zhihu login PROFILE",
      "logout_command": "chatpost zhihu logout PROFILE",
      "name": "zhihu",
      "profiles_command": "chatpost zhihu profiles",
      "status_command": "chatpost zhihu status PROFILE"
    }
  ],
  "status": "READY"
}
```

### profiles_old

```bash
$ chatpost profiles --platform zhihu --registry /home/zhihong/Playground/projects/chatarch/08-05-chatpost-login-cli-practice/playground/accounts.toml --output json -I
exit: 0
stdout:
{
  "platform": "zhihu",
  "profiles": [
    {
      "alias": "zhihu-test",
      "label": "Logged-in Zhihu profile; keep this existing session",
      "platform": "zhihu",
      "profile": "zhihu-test",
      "runner_config": "/home/zhihong/Playground/projects/chatarch/08-05-chatpost-login-cli-practice/playground/runner-attach-existing.toml"
    },
    {
      "alias": "zhihu-qr-login",
      "label": "Zhihu QR authorization login checkpoint for adding a new account",
      "login_methods": [
        "qr"
      ],
      "platform": "zhihu",
      "profile": "zhihu-qr-login",
      "runner_config": "/home/zhihong/Playground/projects/chatarch/08-05-chatpost-login-cli-practice/playground/runner-qr-login.toml"
    }
  ],
  "status": "READY"
}
```

### zhihu_profiles_old

```bash
$ chatpost zhihu profiles --registry /home/zhihong/Playground/projects/chatarch/08-05-chatpost-login-cli-practice/playground/accounts.toml --output json -I
exit: 0
stdout:
{
  "platform": "zhihu",
  "profiles": [
    {
      "alias": "zhihu-test",
      "label": "Logged-in Zhihu profile; keep this existing session",
      "platform": "zhihu",
      "profile": "zhihu-test",
      "runner_config": "/home/zhihong/Playground/projects/chatarch/08-05-chatpost-login-cli-practice/playground/runner-attach-existing.toml"
    },
    {
      "alias": "zhihu-qr-login",
      "label": "Zhihu QR authorization login checkpoint for adding a new account",
      "login_methods": [
        "qr"
      ],
      "platform": "zhihu",
      "profile": "zhihu-qr-login",
      "runner_config": "/home/zhihong/Playground/projects/chatarch/08-05-chatpost-login-cli-practice/playground/runner-qr-login.toml"
    }
  ],
  "status": "READY"
}
```

### zhihu_test_status

```bash
$ chatpost zhihu status zhihu-test --registry /home/zhihong/Playground/projects/chatarch/08-05-chatpost-login-cli-practice/playground/accounts.toml --output json -I
exit: 0
stdout:
{
  "account_name": "[REDACTED]",
  "account_url": "[URL_REDACTED]",
  "browser_attachment": "EXISTING_CDP",
  "browser_cdp_product": "Chrome/145.0.7632.6",
  "browser_revision": "existing-cdp",
  "browser_version": "145.0.7632.6",
  "check_method": "browser_page",
  "platform": "zhihu",
  "playwright_version": "1.61.1",
  "profile": "zhihu-test",
  "status": "LOGGED_IN",
  "target": "zhihu@zhihu-test"
}
```

### zhihu_test_login

```bash
$ chatpost zhihu login zhihu-test --registry /home/zhihong/Playground/projects/chatarch/08-05-chatpost-login-cli-practice/playground/accounts.toml --timeout 5 --output json -I
exit: 0
stdout:
{"account_name": "[REDACTED]", "account_url": "[URL_REDACTED]", "browser_attachment": "EXISTING_CDP", "browser_cdp_product": "Chrome/145.0.7632.6", "browser_revision": "existing-cdp", "browser_version": "145.0.7632.6", "check_method": "browser_page", "event": "already_logged_in", "platform": "zhihu", "playwright_version": "1.61.1", "profile": "zhihu-test", "status": "LOGGED_IN", "target": "zhihu@zhihu-test"}
```

### zhihu_qr_login_status

```bash
$ chatpost zhihu status zhihu-qr-login --registry /home/zhihong/Playground/projects/chatarch/08-05-chatpost-login-cli-practice/playground/accounts.toml --output json -I
exit: 0
stdout:
{
  "account_name": "[REDACTED]",
  "account_url": "[URL_REDACTED]",
  "browser_attachment": "OWNED_BROWSER",
  "browser_revision": "1228",
  "browser_version": "149.0.7827.55",
  "check_method": "browser_page",
  "platform": "zhihu",
  "playwright_version": "1.61.1",
  "profile": "zhihu-qr-login",
  "status": "LOGGED_IN",
  "target": "zhihu@zhihu-qr-login"
}
```

### zhihu_qr_login_login

```bash
$ chatpost zhihu login zhihu-qr-login --registry /home/zhihong/Playground/projects/chatarch/08-05-chatpost-login-cli-practice/playground/accounts.toml --timeout 5 --output json -I
exit: 0
stdout:
{"account_name": "[REDACTED]", "account_url": "[URL_REDACTED]", "browser_attachment": "OWNED_BROWSER", "browser_revision": "1228", "browser_version": "149.0.7827.55", "check_method": "browser_page", "event": "already_logged_in", "platform": "zhihu", "playwright_version": "1.61.1", "profile": "zhihu-qr-login", "status": "LOGGED_IN", "target": "zhihu@zhihu-qr-login"}
```

### practice_status

```bash
$ chatpost zhihu status zhihu-practice-quickstart --registry /home/zhihong/Playground/projects/chatarch/08-05-chatpost-login-cli-practice/playground/quickstart-practice-20260807-182534/accounts.toml --output json -I
exit: 0
stdout:
{
  "browser_attachment": "OWNED_BROWSER",
  "browser_revision": "1228",
  "browser_version": "149.0.7827.55",
  "check_method": "browser_page",
  "platform": "zhihu",
  "playwright_version": "1.61.1",
  "profile": "zhihu-practice-quickstart",
  "status": "LOGGED_OUT",
  "target": "zhihu@zhihu-practice-quickstart"
}
```

### practice_login_timeout_smoke

This short timeout smoke proves the command emits the page-owned login handoff immediately even when the user does not finish authorization inside the short test window.

```bash
$ chatpost zhihu login zhihu-practice-quickstart --registry /home/zhihong/Playground/projects/chatarch/08-05-chatpost-login-cli-practice/playground/quickstart-practice-20260807-182534/accounts.toml --timeout 5 --output json -I
exit: 0
stdout:
{"browser_attachment": "OWNED_BROWSER", "browser_revision": "1228", "browser_version": "149.0.7827.55", "check_method": "browser_page", "event": "login_url", "handoff_kind": "page_owned_login_url", "login_url": "[LIVE_LOGIN_URL_OMITTED_FROM_PUBLIC_DOC]", "platform": "zhihu", "playwright_version": "1.61.1", "profile": "zhihu-practice-quickstart", "status": "LOGIN_REQUIRED", "target": "zhihu@zhihu-practice-quickstart"}
{"browser_attachment": "OWNED_BROWSER", "browser_revision": "1228", "browser_version": "149.0.7827.55", "check_method": "browser_page", "event": "login_timeout", "handoff_kind": "page_owned_login_url", "login_url": "[LIVE_LOGIN_URL_OMITTED_FROM_PUBLIC_DOC]", "platform": "zhihu", "playwright_version": "1.61.1", "profile": "zhihu-practice-quickstart", "status": "LOGIN_TIMEOUT", "target": "zhihu@zhihu-practice-quickstart"}
```

### practice_login_authorized_end_to_end

This run keeps the same CLI command alive while the user authorizes the page-owned Zhihu login URL. The live tokenized `login_url` and page-visible account identity fields are omitted from the public documentation; the remaining CLI output below is the real command result.

When this login URL is delivered through Feishu/Lark, do not treat a URL button click as observable completion. A URL button only navigates. Pair it with explicit callback buttons such as `I opened the link / authorization done` and `Cancel`, then verify completion by running `chatpost zhihu status PROFILE` or by waiting for this long-running `login` command to emit `LOGGED_IN`.

```bash
$ chatpost zhihu login zhihu-practice-quickstart --registry /home/zhihong/Playground/projects/chatarch/08-05-chatpost-login-cli-practice/playground/quickstart-practice-20260807-182534/accounts.toml --timeout 900 --output json -I
exit: 0
stdout:
{"browser_attachment": "OWNED_BROWSER", "browser_revision": "1228", "browser_version": "149.0.7827.55", "check_method": "browser_page", "event": "login_url", "handoff_kind": "page_owned_login_url", "login_url": "[LIVE_LOGIN_URL_OMITTED_FROM_PUBLIC_DOC]", "platform": "zhihu", "playwright_version": "1.61.1", "profile": "zhihu-practice-quickstart", "status": "LOGIN_REQUIRED", "target": "zhihu@zhihu-practice-quickstart"}
{"account_name": "[REDACTED]", "account_url": "[URL_REDACTED]", "browser_attachment": "OWNED_BROWSER", "browser_revision": "1228", "browser_version": "149.0.7827.55", "check_method": "browser_page", "event": "logged_in", "platform": "zhihu", "playwright_version": "1.61.1", "profile": "zhihu-practice-quickstart", "status": "LOGGED_IN", "target": "zhihu@zhihu-practice-quickstart"}
```

### practice_status_after_authorization

```bash
$ chatpost zhihu status zhihu-practice-quickstart --registry /home/zhihong/Playground/projects/chatarch/08-05-chatpost-login-cli-practice/playground/quickstart-practice-20260807-182534/accounts.toml --output json -I
exit: 0
stdout:
{
  "account_name": "[REDACTED]",
  "account_url": "[URL_REDACTED]",
  "browser_attachment": "OWNED_BROWSER",
  "browser_revision": "1228",
  "browser_version": "149.0.7827.55",
  "check_method": "browser_page",
  "platform": "zhihu",
  "playwright_version": "1.61.1",
  "profile": "zhihu-practice-quickstart",
  "status": "LOGGED_IN",
  "target": "zhihu@zhihu-practice-quickstart"
}
```
