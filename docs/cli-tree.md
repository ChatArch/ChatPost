# CLI 树

`ChatPost 0.1.x` 当前只暴露浏览器级登录基础层：平台发现、Profile 发现，以及知乎 `profiles/login/status/logout`。本轮不注册草稿、发布、QR artifact、account helper 或发布适配器命令。

这里的 `PROFILE` 是 registry alias / 浏览器用户数据目录 / 登录态容器，不是知乎账号 ID、Cookie、LocalStorage、IndexedDB、session 或 token。

## 当前真实命令

`chatpost --tree` 会打印真实注册 CLI 树：

```text
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
```

## 命令注释

- `chatpost platforms`：列出支持的平台；不启动浏览器，不读取登录态，不接发布适配器。
- `chatpost profiles [--platform zhihu]`：列出 registry 中的浏览器 Profile；不启动浏览器，不读取登录态，不接发布适配器。
- `chatpost zhihu profiles`：只列知乎 Profile；不启动浏览器，不读取登录态。
- `chatpost zhihu status PROFILE`：启动/连接受控 Chromium Profile，用知乎网页 DOM/URL/可见菜单判断 `LOGGED_IN`、`LOGGED_OUT` 或 `UNKNOWN`；不读取或导出 Cookie、LocalStorage、IndexedDB、session 或 token。
- `chatpost zhihu login PROFILE`：先做 browser-page status；已登录直接返回 `LOGGED_IN`；未登录时打开知乎登录页，尽快输出 page-owned `login_url` 或 `browser_opened` handoff，然后保持浏览器等待登录完成。
- `chatpost zhihu logout PROFILE`：先做 browser-page status；未登录返回 `ALREADY_LOGGED_OUT`；已登录才清理知乎 origins 登录态。清理不会读取任何 session 原值。

## 登录 Runner 配置

登录基础层只需要浏览器字段：

```toml
[zhihu]
playwright_version = "1.61.1"
playwright_home = "/absolute/path/to/.chatarch/playwright"
profile_dir = "/absolute/path/to/zhihu-profile"
cdp_host = "127.0.0.1"
cdp_port = 9227
headless = true
browser_args = ["--disable-dev-shm-usage"]
attach_existing_cdp = false
```

安全边界：

- `profile_dir` 必须存在且不得向 group/other 开放；
- CDP 只能绑定数值 IPv4 loopback `127.0.0.1`；
- `browser_args` 不能覆盖 Profile、CDP 或 extension 所有权参数；
- registry/config/output 不保存 Cookie、LocalStorage、IndexedDB、session、验证码、手机号、密码或 token。

## 明确不在本轮 CLI 中

account helper、QR helper、知乎 account helper、draft、verify、doctor 都不是本轮登录基础层，不注册为当前用户可见或隐藏命令。

以后如果要做发布、草稿或发布适配器验证，应作为独立 PR 和独立命令面设计，不能污染 `login/status/logout` 的纯浏览器语义。
