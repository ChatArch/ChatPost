# 能力地图

本页区分 `ChatPost 0.1.x` 当前真实用户入口和仍属后续工作的边界。

## 已实现

| 能力 | 状态 | 说明 |
|---|---|---|
| CLI 基础入口 | 已实现 | `chatpost --help`、`--version`、`--tree`；`--tree` 打印真实注册 CLI 树。 |
| 平台与 Profile 发现 | 已实现 | `chatpost platforms`、`chatpost profiles --platform zhihu` 和 `chatpost zhihu profiles` 只读 registry metadata；不启动浏览器，不读取登录态，不输出 Cookie、LocalStorage、token、password 或 credential。 |
| 知乎纯浏览器登录/状态/登出 | 已实现 | `chatpost zhihu login/status/logout PROFILE` 只操作受控 Chromium Profile。`status` 用页面 DOM/URL/可见账号入口判断 `LOGGED_IN`、`LOGGED_OUT` 或 `UNKNOWN`；`login` 已登录直接返回，未登录时输出 page-owned `login_url` 或 `browser_opened` handoff；`logout` 先 status，未登录 no-op，已登录才清理知乎 origins。全程不调用发布适配器、不加载发布扩展、不要求发布 token、不读取或导出 Cookie/LocalStorage/IndexedDB/session/token。 |
| Browser-only runner config | 已实现 | 登录基础层只需要 `playwright_version`、`playwright_home`、`profile_dir`、`cdp_host`、`cdp_port`、`headless`、`browser_args`、`attach_existing_cdp`。 |
| Secret redaction / state boundary | 已实现 | 输出只包含页面可见账号名/主页 URL 等非 secret 状态；诊断继续遮蔽 WebSocket、loopback、ownership marker 和私密赋值。 |

## 已验证事实

- 单元测试锁定 login-only CLI：`platforms`、`profiles`、`zhihu profiles/login/status/logout`。
- 单元测试锁定 `load_browser_config` 不需要 adapter/env/extension 字段。
- 单元测试锁定 browser-only Chrome 启动命令不带 `--load-extension` / `--disable-extensions-except`。
- 单元测试锁定 `status/login/logout` 走 browser-level API，而不是发布适配器 auth。

## 责任边界

| Owner | 负责 | 不负责 |
|---|---|---|
| ChatUp | Playwright package/browser 安装、版本、revision、路径、doctor | Profile、登录状态判断 |
| ChatBrowser | 浏览器 runtime、Profile metadata、CDP session metadata | 平台 adapter、内容发布、Cookie 导出 |
| ChatPost | Profile alias、受控 Chromium lifecycle、CDP、网页登录状态判断、login handoff、logout 清理 | 下载 browser、读取 secrets、最终发布、平台 media 上传 |
| 人工 | 首次登录、滑块/验证码、最终账号确认 | 自动化 secret 导出 |

## 不在当前登录基础层

- `chatpost account ...`；
- `chatpost qr ...`；
- `chatpost zhihu account ...`；
- `chatpost zhihu draft ...`；
- 发布适配器 verify/doctor；
- same-ID 文章更新；
- 自动最终发布。

这些能力若需要，应另起独立设计和 PR，不能改变 `login/status/logout` 的纯浏览器语义。
