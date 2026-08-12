# CLI 树

`ChatPost 0.1.x` 当前暴露三层能力：

1. 浏览器级登录基础层：平台发现、Profile 发现，以及知乎/小红书/CSDN `profiles/login/status/logout`。
2. 独立 Wechatsync draft 入口：`chatpost zhihu draft PROFILE SOURCE` 与 `chatpost csdn draft PROFILE SOURCE` 可 dry-run 或创建一个草稿，且都不最终发布。
3. 小红书当前只保留 QR 登录基础层，草稿/发布仍不在当前用户可见 CLI。

这里的 `PROFILE` 是 registry alias / 浏览器用户数据目录 / 登录态容器，不是平台账号 ID、Cookie、LocalStorage、IndexedDB、session 或 token。`draft` 复用同一个 Profile，但不会改变 `login/status/logout` 的纯浏览器语义。

## 当前真实命令

`chatpost --tree` 会打印真实注册 CLI 树：

```text
chatpost  # Browser-level platform login and draft manager.
├── --help  # Show help for the current command.
├── --version  # Show package version.
├── --tree  # Print the registered CLI tree with command purpose and IO shape.
├── platforms [--output text|json] [-I/--no-interactive]  # List supported platforms without starting a browser.
├── profiles [--platform zhihu|xhs|csdn] [--registry REGISTRY] [--output text|json] [-I/--no-interactive]  # List configured browser Profiles without checking login state.
├── zhihu  # Zhihu browser login and Wechatsync draft capabilities.
│   ├── profiles [--registry REGISTRY] [--output text|json] [-I/--no-interactive]  # List configured Zhihu browser Profiles.
│   ├── status PROFILE [--registry REGISTRY] [--output text|json] [-I/--no-interactive]  # Check PROFILE's Zhihu web login state from browser-visible page state.
│   ├── login PROFILE [--registry REGISTRY] [--timeout TIMEOUT] [--output text|json] [-I/--no-interactive]  # Open/check a pure browser login session and emit a page-owned handoff.
│   ├── logout PROFILE [--registry REGISTRY] [--output text|json] [-I/--no-interactive]  # Log out or clear PROFILE's Zhihu browser state after browser-level status.
│   └── draft PROFILE SOURCE [--registry REGISTRY] [--dry-run] [--receipt RECEIPT] [--output text|json] [-I/--no-interactive]  # Dry-run or create one Zhihu draft through Wechatsync; never final-publish.
├── xhs  # XHS browser login system.
│   ├── profiles [--registry REGISTRY] [--output text|json] [-I/--no-interactive]  # List configured XHS browser Profiles.
│   ├── status PROFILE [--registry REGISTRY] [--output text|json] [-I/--no-interactive]  # Check PROFILE's XHS web login state from browser-visible page state.
│   ├── login PROFILE [--registry REGISTRY] [--timeout TIMEOUT] [--qrcode QRCODE-PATH] [--output text|json] [-I/--no-interactive]  # Open/check a pure browser login session and emit a page-owned handoff.
│   └── logout PROFILE [--registry REGISTRY] [--output text|json] [-I/--no-interactive]  # Log out or clear PROFILE's XHS browser state after browser-level status.
└── csdn  # CSDN browser login and Wechatsync draft capabilities.
    ├── profiles [--registry REGISTRY] [--output text|json] [-I/--no-interactive]  # List configured CSDN browser Profiles.
    ├── status PROFILE [--registry REGISTRY] [--output text|json] [-I/--no-interactive]  # Check PROFILE's CSDN web login state from browser-visible page state.
    ├── login PROFILE [--registry REGISTRY] [--timeout TIMEOUT] [--qrcode QRCODE-PATH] [--output text|json] [-I/--no-interactive]  # Open/check a pure browser login session and emit a page-owned handoff.
    ├── logout PROFILE [--registry REGISTRY] [--output text|json] [-I/--no-interactive]  # Log out or clear PROFILE's CSDN browser state after browser-level status.
    └── draft PROFILE SOURCE [--registry REGISTRY] [--dry-run] [--receipt RECEIPT] [--output text|json] [-I/--no-interactive]  # Dry-run or create one CSDN draft through Wechatsync; never final-publish.
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
chatpost csdn --help
chatpost csdn profiles --help
chatpost csdn login --help
chatpost csdn status --help
chatpost csdn logout --help
chatpost csdn draft --help
```

## 命令注释

- `chatpost platforms`：列出支持的平台；不启动浏览器，不读取登录态，不接发布适配器。
- `chatpost profiles [--platform zhihu|xhs|csdn]`：列出 registry 中的浏览器 Profile；不启动浏览器，不读取登录态，不接发布适配器。
- `chatpost <platform> profiles`：只列对应平台 Profile；不启动浏览器，不读取登录态。
- `chatpost zhihu status PROFILE` / `chatpost xhs status PROFILE` / `chatpost csdn status PROFILE`：启动/连接受控 Chromium Profile，用平台网页 DOM/URL/可见菜单判断 `LOGGED_IN`、`LOGGED_OUT` 或 `UNKNOWN`；不读取或导出 Cookie、LocalStorage、IndexedDB、session 或 token。
- `chatpost zhihu login PROFILE`：先做 browser-page status；已登录直接返回 `LOGGED_IN`；未登录时打开知乎登录页，尽快输出 page-owned `login_url` 或 `browser_opened` handoff，然后保持浏览器等待登录完成。
- `chatpost xhs login PROFILE --qrcode PATH`：先做 browser-page status；已登录直接返回 `LOGGED_IN`；未登录时打开小红书创作者中心登录页，切到二维码登录，写出 mode `0600` 的二维码 PNG，并只输出 `qrcode_path`。用户可见输出不暴露 `login_url`、`loginconfirm`、raw data URL、base64 或二维码 token。
- `chatpost csdn login PROFILE --qrcode PATH`：先做 browser-page status；已登录直接返回 `LOGGED_IN`；未登录时打开 CSDN 登录页，写出 mode `0600` 的二维码 PNG，并只输出 `qrcode_path`。密码/SMS/人机验证属于人工浏览器流程，CLI 不绕过、不打码、不保存验证码。
- `chatpost zhihu logout PROFILE` / `chatpost xhs logout PROFILE` / `chatpost csdn logout PROFILE`：先做 browser-page status；未登录返回 `ALREADY_LOGGED_OUT`；已登录才清理对应平台 origins 登录态。清理不会读取任何 session 原值。
- `chatpost zhihu draft PROFILE SOURCE --dry-run` / `chatpost csdn draft PROFILE SOURCE --dry-run`：通过 Wechatsync 解析源文档并返回 `DRY_RUN_OK`/preview，不启动浏览器，不写草稿。
- `chatpost zhihu draft PROFILE SOURCE --receipt PATH` / `chatpost csdn draft PROFILE SOURCE --receipt PATH`：启动配置好的浏览器/Profile/extension/bridge，通过 Wechatsync 创建一个草稿，写入 mode `0600` receipt，并返回 `DRAFT_CREATED`、`draft_id` 和 review URL；不点击最终发布。

## 登录 Runner 配置

登录基础层只需要浏览器字段；知乎、小红书和 CSDN 使用同形 TOML，仅 table 名不同：

```toml
[csdn]
playwright_version = "1.61.1"
playwright_home = "/absolute/path/to/.chatarch/playwright"
profile_dir = "/absolute/path/to/csdn-profile"
cdp_host = "127.0.0.1"
cdp_port = 9284
headless = true
browser_args = ["--disable-dev-shm-usage"]
attach_existing_cdp = false
```

## Draft Runner 配置

知乎与 CSDN 的 `draft` 需要完整 runner 字段：browser/Profile 字段，加上 extension、Node、Wechatsync CLI、私有 env 文件和 bridge loopback 端口。小红书当前没有用户可见 draft/create 命令；`xhs login/status/logout` 只读取 `[xhs]` 浏览器字段，不读取 adapter token，也不连接发布扩展。

安全边界：

- `profile_dir` 必须存在且不得向 group/other 开放；
- CDP 和 bridge 只能绑定数值 IPv4 loopback `127.0.0.1`；
- `browser_args` 不能覆盖 Profile、CDP 或 extension 所有权参数；
- registry/config/output 不保存 Cookie、LocalStorage、IndexedDB、session、验证码、手机号、密码或 token；
- 知乎/CSDN `draft create` 只创建草稿，不最终发布；如果结果是 `RESULT_UNKNOWN`，receipt 会保留证据，调用方不能自动重试；
- 当前 Wechatsync CSDN adapter 能力是 `draft`：请求写 `pubStatus="draft"`，不提供 ChatPost 可调用的公开 `post/publish` 路径；
- 小红书草稿/发布不在当前用户可见 CLI；后续若接入 adapter，必须另设独立命令面，不能从 `login/status/logout` 暗中写远端。

## 仍不在当前 CLI 中

account helper、QR helper、平台 account helper、verify、doctor、小红书 draft/create、same-ID 更新和最终公开发布都不是当前用户可见命令。

后续如果要做发布适配器 verify/doctor、same-ID 更新或最终公开发布，应作为独立 PR 和独立命令面设计，不能污染 `login/status/logout` 的纯浏览器语义。
