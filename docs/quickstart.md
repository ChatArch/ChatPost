# Quickstart：逻辑 Profile、知乎登录与草稿

本页覆盖 ChatPost 的推荐日常路径：用逻辑 Profile（默认 `test`，可另建 `product`）发现配置、检查知乎网页登录态、打开登录 handoff、登出/清理；再通过独立 `chatpost zhihu draft` 入口 dry-run 或创建一个知乎草稿。`login/status/logout` 不创建草稿、不调用发布适配器，也不会读取或导出 Cookie、LocalStorage、IndexedDB、session 或 token 原值。小红书保留同形 `profiles/login/status/logout` 接口，但当前不作为验收主线。

## 0. 安装链路与职责边界

安装 ChatPost 会带上 Python 层依赖 `chatup` 和 `chatbrowser`，但三者职责不同：

```text
ChatUp       = 安装 / setup：Node、Playwright package、Chromium/Chrome 制品
ChatBrowser  = 浏览器运行态：backend、Profile metadata、loopback CDP session registry
ChatPost     = post 编排：逻辑 Profile -> 平台 -> 登录态 -> draft/create receipt
```

```bash
python -m pip install ChatPost
chatpost --version
chatup playwright install 1.61.1 --browser chromium --output json -I
chatbrowser profile create zhihu-test \
  --path "$HOME/.chatarch/chatpost/profiles/test/zhihu" \
  --backend chatup-playwright \
  --label owner=chatpost \
  --label platform=zhihu \
  --label logical_profile=test \
  --output json
```

`pip install ChatPost` 负责安装 Python 包依赖；浏览器二进制仍由 `chatup playwright install ...` 准备；浏览器 Profile 路径和非敏感 metadata 由 `chatbrowser profile create ...` 登记。ChatPost 的 runner 可以通过 `browser_profile = "zhihu-test"` 引用 ChatBrowser Profile，并继续把 Wechatsync extension、bridge、receipt 等发布适配器字段留在 ChatPost/adapter 层。

## 0b. 设定变量

```bash
CHATPOST=chatpost
CHATPOST_HOME="${CHATPOST_HOME:-$HOME/.chatarch/chatpost}"
REGISTRY="${CHATPOST_ACCOUNT_REGISTRY:-$CHATPOST_HOME/accounts.toml}"
PROFILE=test
```

ChatPost 默认把本地状态放在 ChatArch 内部目录 `~/.chatarch/chatpost/`：默认 registry 是 `~/.chatarch/chatpost/accounts.toml`，runner/Profile/receipt 等后续状态也应放在这个 state root 下。`--registry` 只用于显式覆盖或任务级实验；不要把默认 `accounts.toml` 放到仓库根目录、当前工作目录或临时 project 目录。

`accounts.toml` 只保存非敏感 Profile metadata，例如 alias、platform、runner_config、profile 和 label。不要把 Cookie、LocalStorage、二维码 payload、验证码、手机号、密码、token 或 WebSocket UUID 写入 registry、config、日志或文档。相对 `runner_config` 路径按 registry 所在目录解析，因此默认情况下也会落在 `~/.chatarch/chatpost/` 内部。

推荐只维护两个逻辑 Profile：

```text
profiles/
  test/
    zhihu/
    xhs/
  product/
    zhihu/
    xhs/
```

日常命令优先使用逻辑名，例如 `chatpost zhihu status test`。registry 内部可以保留平台别名（如 `zhihu-test`、`xhs-test`）作为兼容层，但用户不需要记这些别名。

## 1. 确认可见 CLI 和 Profile

```bash
"$CHATPOST" --tree

"$CHATPOST" platforms   --output json   -I

"$CHATPOST" profiles   --platform zhihu   --registry "$REGISTRY"   --output json   -I

"$CHATPOST" profiles   --platform xhs   --registry "$REGISTRY"   --output json   -I

"$CHATPOST" zhihu profiles   --registry "$REGISTRY"   --output json   -I

"$CHATPOST" xhs profiles   --registry "$REGISTRY"   --output json   -I
```

这些发现命令只读 registry，不启动浏览器，不读取登录态。等价真实命令名是 `chatpost platforms`、`chatpost profiles`、`chatpost zhihu profiles` 和 `chatpost xhs profiles`。

登录基础层的真实命令名是 `chatpost zhihu status`、`chatpost zhihu login`、`chatpost zhihu logout`、`chatpost xhs status`、`chatpost xhs login` 和 `chatpost xhs logout`。

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

## 5b. 小红书接口保留（当前不作为验收主线）

小红书保留与知乎同形的平台入口：`profiles/status/login/logout`。当前默认推荐仍只验收知乎；小红书二维码来源需要后续单独修正普通站点登录页后再恢复验收。日常不要把小红书调试二维码当作可用登录结果。

```bash
XHS_PROFILE="$PROFILE"
XHS_QR="$CHATPOST_HOME/xhs-login-qrcode.png"
"$CHATPOST" xhs status "$XHS_PROFILE"   --registry "$REGISTRY"   --output json   -I
# 后续恢复 XHS 验收时再执行：
# "$CHATPOST" xhs login "$XHS_PROFILE"   --registry "$REGISTRY"   --timeout 900   --qrcode "$XHS_QR"   --output json   -I
```

当二维码成功生成时，首个 JSON Lines 事件形态为 `event=login_handoff`、`status=LOGIN_REQUIRED`、`handoff_kind=qrcode_image`、`qrcode_path=/path/to/png`。如果页面没有暴露真实可解码二维码，返回 `LOGIN_HANDOFF_UNAVAILABLE` / `reason=qrcode_not_found`；如果小红书把当前网络判为风险，返回 `LOGIN_BLOCKED` / `block_reason=network_risk`。这些失败都不能伪装成可扫码二维码。

## 常见停点

| 停点 | 处理 |
| --- | --- |
| `login` 直接返回 `LOGGED_IN` | 预期行为，说明 Profile 已登录。 |
| `xhs login` 输出 `qrcode_path` | 预期 handoff；把该 PNG 发给用户扫码，并保持同一登录命令/浏览器页继续轮询。 |
| `xhs login` 返回 `LOGIN_HANDOFF_UNAVAILABLE` / `qrcode_not_found` | 页面未暴露真实可解码二维码；不能把截图、切换图标或私有 artifact 冒充二维码。 |
| `zhihu login` 输出 `browser_opened` 但没有 page-owned `login_url` | 浏览器已打开等待人工登录；不要用截图或私有 artifact 冒充登录链接。 |
| 登录页需要滑块或验证码 | 停在人工浏览器流程，不把验证码写进 CLI 参数或日志。 |
| `login` 返回 `LOGIN_BLOCKED` / `block_reason=network_risk` | 当前出口被平台拒绝，不能生成可扫码二维码；换可靠网络或本机浏览器 profile 后再试。 |
| `status` 返回 `UNKNOWN` | 只报告未知；不要 fallback 到发布适配器或读取 Cookie/token。 |

## 6. 知乎草稿 dry-run 与 create

`chatpost zhihu draft` 与浏览器级登录命令刻意分离。它复用同一个逻辑 Profile，但只有 draft 流程会加载 Wechatsync、扩展、bridge 和私有 env 文件；`login/status/logout` 必须保持 browser-only。

```bash
ARTICLE=/absolute/path/to/article.md
chatpost zhihu draft "$PROFILE" "$ARTICLE" \
  --registry "$REGISTRY" \
  --dry-run \
  --output json \
  -I
```

真实 create 需要显式 receipt，并且只创建一个知乎草稿，不最终发布：

```bash
RECEIPT="$CHATPOST_HOME/runners/zhihu-test/run/zhihu-draft-receipt.json"
chatpost zhihu draft "$PROFILE" "$ARTICLE" \
  --registry "$REGISTRY" \
  --receipt "$RECEIPT" \
  --output json \
  -I
```

期望状态：dry-run 返回 `DRY_RUN_OK`；真实 create 返回 `DRAFT_CREATED` 并写 mode `0600` receipt。若返回 `RESULT_UNKNOWN`，不要自动重试，先读 receipt 和浏览器状态。
