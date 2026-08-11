# 能力地图

本页区分 `ChatPost 0.1.x` 当前真实用户入口、`login/status/logout` 的纯浏览器边界、Wechatsync 草稿边界，以及仍属后续工作的能力。

## 已实现

| 能力 | 状态 | 说明 |
|---|---|---|
| CLI 基础入口 | 已实现 | `chatpost --help`、`--version`、`--tree`；`--tree` 打印真实注册 CLI 树。 |
| 平台与 Profile 发现 | 已实现 | `chatpost platforms`、`chatpost profiles --platform zhihu|xhs|csdn`、`chatpost zhihu profiles`、`chatpost xhs profiles` 和 `chatpost csdn profiles` 只读 registry metadata；不启动浏览器，不读取登录态，不输出 Cookie、LocalStorage、token、password 或 credential。 |
| 知乎纯浏览器登录/状态/登出 | 已实现 | `chatpost zhihu login/status/logout PROFILE` 只操作受控 Chromium Profile。`status` 用页面 DOM/URL/可见账号入口判断 `LOGGED_IN`、`LOGGED_OUT` 或 `UNKNOWN`；`login` 已登录直接返回，未登录时输出 page-owned `login_url` 或 `browser_opened` handoff；`logout` 先 status，未登录 no-op，已登录才清理知乎 origins。全程不调用发布适配器、不加载发布扩展、不要求发布 token、不读取或导出 Cookie/LocalStorage/IndexedDB/session/token。 |
| 小红书二维码登录/状态/登出 | 已实现 | `chatpost xhs login/status/logout PROFILE` 只操作受控 Chromium Profile。`login` 未登录时切到小红书二维码登录，写出 mode `0600` PNG artifact，并只输出 `qrcode_path`。不暴露 `login_url`、`loginconfirm`、raw data URL、base64 或二维码 token；二维码必须绑定仍然活着、正在轮询的同一浏览器页。 |
| CSDN 二维码登录/状态/登出 | 已实现 | `chatpost csdn login/status/logout PROFILE` 只操作受控 Chromium Profile。`status` 结合 CSDN 页面可见状态和受控浏览器内的用户接口结果判断登录态；`login` 未登录时写出 mode `0600` 二维码 PNG 并只输出 `qrcode_path`。密码/SMS/人机验证属于人工浏览器流程，CLI 不绕过、不打码、不保存验证码。 |
| Browser-only runner config | 已实现 | 登录基础层只需要 `playwright_version`、`playwright_home`、`profile_dir`、`cdp_host`、`cdp_port`、`headless`、`browser_args`、`attach_existing_cdp`；可用 `browser_profile` 引用 ChatBrowser Profile。 |
| ChatArch state root | 已实现 | 默认本地状态根目录是 `~/.chatarch/chatpost/`；默认 registry 是 `~/.chatarch/chatpost/accounts.toml`，可用 `CHATPOST_HOME` / `CHATPOST_ACCOUNT_REGISTRY` / `--registry PATH` 显式覆盖。 |
| 知乎 draft / Wechatsync adapter | 已实现 | `chatpost zhihu draft PROFILE SOURCE --dry-run` 调用 Wechatsync CLI parser 做 adapter preview，不启动浏览器也不写草稿；`--receipt PATH` 启动受控 Chromium + Wechatsync extension，并通过 extension MCP direct bridge 创建一个知乎草稿，写 mode `0600` receipt，返回 `DRAFT_CREATED`、`draft_id` 和 `/edit` review URL；不最终发布，不做 same-ID 更新。 |
| CSDN draft / Wechatsync adapter | 已实现 | `chatpost csdn draft PROFILE SOURCE --dry-run` 与真实 create 都走 Wechatsync adapter；CSDN create 只接受 Wechatsync 返回的 `draftOnly=true` 草稿结果，写 mode `0600` receipt，返回 `DRAFT_CREATED`、`draft_id` 和 CSDN editor review URL；不手写 CSDN editor DOM/CDP 自动化，也不最终公开发布。 |
| Secret redaction / state boundary | 已实现 | 输出只包含页面可见账号名/主页 URL 等非 secret 状态；诊断继续遮蔽 WebSocket、loopback、ownership marker 和私密赋值。 |

## 已验证事实

- 单元测试锁定 CLI：`platforms`、`profiles`、`zhihu profiles/login/status/logout/draft`、`xhs profiles/login/status/logout` 和 `csdn profiles/login/status/logout/draft`。
- 单元测试锁定 `load_browser_config` 不需要 adapter/env/extension 字段。
- 单元测试锁定 browser-only Chrome 启动命令不带 `--load-extension` / `--disable-extensions-except`。
- 单元测试锁定 `status/login/logout` 走 browser-level API，而不是发布适配器 auth；XHS/CSDN login 输出二维码 artifact，不把内部确认链接/token 作为用户接口。
- 单元测试锁定 Zhihu/CSDN `draft` 走 `load_runner_config` / `execute_task`，create 前必须显式传 `--receipt`，receipt 写入 mode `0600`。
- CSDN Wechatsync adapter 的当前能力是草稿：请求使用 `pubStatus="draft"`，返回 `draftOnly=true`；ChatPost 当前没有 CSDN 公开 `post/publish` 命令。

## 责任边界

| Owner | 负责 | 不负责 |
|---|---|---|
| ChatUp | Playwright package/browser 安装、版本、revision、路径、doctor | Profile、登录状态判断 |
| ChatBrowser | 浏览器 runtime、Profile metadata、CDP session metadata | 平台 adapter、内容发布、Cookie 导出 |
| ChatPost | Profile alias、ChatArch-owned state root、受控 Chromium lifecycle、CDP、网页登录状态判断、login handoff、logout 清理、Wechatsync draft orchestration | 下载 browser、读取 secrets、最终发布、平台 media 上传 |
| Wechatsync | 具体平台 draft adapter，包括 Zhihu/CSDN 草稿写入 | ChatPost Profile registry、ChatBrowser metadata、最终人工 review 决策 |
| 人工 | 首次登录、滑块/验证码、最终账号确认、draft review 后人工发布 | 自动化 secret 导出 |

## 不在 login/status/logout 登录基础层

- `chatpost zhihu draft ...` / `chatpost csdn draft ...` 已实现，但它们是独立发布 adapter 入口，不在 `login/status/logout` 登录基础层；
- `chatpost account ...`；
- `chatpost qr ...`；
- 平台 account helper；
- `chatpost xhs draft/create ...`；
- 发布适配器 verify/doctor；
- same-ID 文章更新；
- 自动最终公开发布。

这些后续能力若需要，应另起独立设计和 PR，不能改变 `login/status/logout` 的纯浏览器语义。
