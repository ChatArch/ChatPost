# Quickstart：纯浏览器登录

本页只覆盖 ChatPost 的登录基础层：发现 Profile、检查知乎网页登录态、打开登录 handoff、以及登出/清理。它不创建草稿、不发布内容、不调用发布适配器，也不会读取或导出 Cookie、LocalStorage、IndexedDB、session 或 token 原值。

## 0. 设定变量

```bash
CHATPOST=chatpost
REGISTRY=/absolute/path/to/accounts.toml
PROFILE=zhihu-personal
```

`accounts.toml` 只保存非敏感 Profile metadata，例如 alias、platform、runner_config、profile 和 label。不要把 Cookie、LocalStorage、二维码 payload、验证码、手机号、密码、token 或 WebSocket UUID 写入 registry、config、日志或文档。

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
