# CLI 树

`ChatPost 0.1.x` 当前暴露两层能力：

1. 浏览器级登录基础层：平台发现、Profile 发现，以及知乎/小红书 `profiles/login/status/logout`。
2. 独立知乎 draft 入口：`chatpost zhihu draft PROFILE SOURCE` 可通过 Wechatsync dry-run 或创建一个知乎草稿。小红书草稿/发布尚未进入当前用户可见 CLI。

这里的 `PROFILE` 是 registry alias / 浏览器用户数据目录 / 登录态容器，不是平台账号 ID、Cookie、LocalStorage、IndexedDB、session 或 token。`draft` 复用同一个 Profile，但不会改变 `login/status/logout` 的纯浏览器语义。

## 当前真实命令

`chatpost --tree` 会打印真实注册 CLI 树：

```text
chatpost  # browser-level platform login and draft manager
├── --help  # Show help for the current command.
├── --version  # Show package version.
├── --tree  # Print the registered CLI tree with command purpose and IO shape.
├── platforms [--output text|json] [-I/--no-interactive]  # List supported platforms without starting a browser.
├── profiles [--platform zhihu|xhs] [--registry PATH] [--output text|json] [-I/--no-interactive]  # List configured browser Profiles without checking login state.
├── zhihu  # Zhihu browser login and Wechatsync draft capabilities
    ├── profiles [--registry PATH] [--output text|json] [-I/--no-interactive]  # List configured Zhihu browser Profiles.
    ├── login PROFILE [--registry PATH] [--timeout INTEGER] [--output text|json] [-I/--no-interactive]  # Open/check a pure browser login session; emit page-owned login_url if needed.
    ├── status PROFILE [--registry PATH] [--output text|json] [-I/--no-interactive]  # Check Zhihu web login state from page-visible browser state only.
    ├── logout PROFILE [--registry PATH] [--output text|json] [-I/--no-interactive]  # Log out or clear Zhihu browser state after browser-level status.
    └── draft PROFILE SOURCE [--registry PATH] [--dry-run] [--receipt PATH] [--output text|json] [-I/--no-interactive]  # Dry-run or create one Zhihu draft through Wechatsync; never final-publish.
└── xhs  # XHS browser login system
    ├── profiles [--registry PATH] [--output text|json] [-I/--no-interactive]  # List configured XHS browser Profiles.
    ├── login PROFILE [--registry PATH] [--timeout INTEGER] [--qrcode PATH] [--output text|json] [-I/--no-interactive]  # Wait for the creator login page's own QR handoff and write the QR artifact.
    ├── status PROFILE [--registry PATH] [--output text|json] [-I/--no-interactive]  # Check XHS web login state from page-visible browser state only.
    └── logout PROFILE [--registry PATH] [--output text|json] [-I/--no-interactive]  # Log out or clear XHS browser state after browser-level status.
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
chatpost zhihu status --help
chatpost zhihu logout --help
chatpost zhihu draft --help
chatpost xhs --help
chatpost xhs profiles --help
chatpost xhs login --help
chatpost xhs status --help
chatpost xhs logout --help
```

## 命令注释

- `chatpost platforms`：列出支持的平台；不启动浏览器，不读取登录态，不接发布适配器。
- `chatpost profiles [--platform zhihu|xhs]`：列出 registry 中的浏览器 Profile；不启动浏览器，不读取登录态，不接发布适配器。
- `chatpost zhihu profiles` / `chatpost xhs profiles`：只列对应平台 Profile；不启动浏览器，不读取登录态。
- `chatpost zhihu status PROFILE` / `chatpost xhs status PROFILE`：启动/连接受控 Chromium Profile，用平台网页 DOM/URL/可见菜单判断 `LOGGED_IN`、`LOGGED_OUT` 或 `UNKNOWN`；不读取或导出 Cookie、LocalStorage、IndexedDB、session 或 token。
- `chatpost zhihu login PROFILE`：先做 browser-page status；已登录直接返回 `LOGGED_IN`；未登录时打开知乎登录页，尽快输出 page-owned `login_url` 或 `browser_opened` handoff，然后保持浏览器等待登录完成。
- `chatpost xhs login PROFILE --qrcode PATH`：先做 browser-page status；已登录直接返回 `LOGGED_IN`；未登录时打开小红书创作者中心登录页，切到二维码登录，写出 mode `0600` 的二维码 PNG，并只输出 `qrcode_path`。用户可见输出不暴露 `login_url`、`loginconfirm`、raw data URL、base64 或二维码 token。小红书若遇到平台网络风险拦截，会返回 `LOGIN_BLOCKED` / `block_reason=network_risk`，不会把 fallback 登录页伪装成二维码。
- `chatpost zhihu logout PROFILE` / `chatpost xhs logout PROFILE`：先做 browser-page status；未登录返回 `ALREADY_LOGGED_OUT`；已登录才清理对应平台 origins 登录态。清理不会读取任何 session 原值。
- `chatpost zhihu draft PROFILE SOURCE --dry-run`：通过 Wechatsync 解析源文档并返回 `DRY_RUN_OK`/preview，不启动浏览器，不写草稿。
- `chatpost zhihu draft PROFILE SOURCE --receipt PATH`：启动配置好的浏览器/Profile/extension/bridge，通过 Wechatsync 创建一个知乎草稿，写入 mode `0600` receipt，并返回 `DRAFT_CREATED`、`draft_id` 和 `/edit` review URL；不点击最终发布。

## 登录 Runner 配置

登录基础层只需要浏览器字段；知乎和小红书使用同形 TOML，仅 table 名不同：

```toml
[xhs]
playwright_version = "1.61.1"
playwright_home = "/absolute/path/to/.chatarch/playwright"
profile_dir = "/absolute/path/to/xhs-profile"
cdp_host = "127.0.0.1"
cdp_port = 9237
headless = true
browser_args = ["--disable-dev-shm-usage"]
attach_existing_cdp = false
```

## Draft Runner 配置

知乎 `draft` 需要完整 runner 字段：browser/Profile 字段，加上 extension、Node、Wechatsync CLI、私有 env 文件和 bridge loopback 端口。小红书当前没有用户可见 draft/create 命令；`xhs login/status/logout` 只读取 `[xhs]` 浏览器字段，不读取 adapter token，也不连接发布扩展。

安全边界：

- `profile_dir` 必须存在且不得向 group/other 开放；
- CDP 和 bridge 只能绑定数值 IPv4 loopback `127.0.0.1`；
- `browser_args` 不能覆盖 Profile、CDP 或 extension 所有权参数；
- registry/config/output 不保存 Cookie、LocalStorage、IndexedDB、session、验证码、手机号、密码或 token；
- 知乎 `draft create` 只创建草稿，不最终发布；如果结果是 `RESULT_UNKNOWN`，receipt 会保留证据，调用方不能自动重试；
- 小红书草稿/发布不在当前用户可见 CLI；后续若接入 adapter，必须另设独立命令面，不能从 `login/status/logout` 暗中写远端。

## 仍不在当前 CLI 中

account helper、QR helper、平台 account helper、verify、doctor、小红书 draft/create、same-ID 更新和最终发布都不是当前用户可见命令。

后续如果要做发布适配器 verify/doctor、same-ID 更新或最终发布，应作为独立 PR 和独立命令面设计，不能污染 `login/status/logout` 的纯浏览器语义。
