# Quickstart：从登录到发送草稿

本页是 ChatPost 的日常最短路径：确认 Profile、登录知乎、dry-run 文章、把文章发送到知乎 **review 草稿**。它不会点击最终发布，也不会读取或导出 Cookie、LocalStorage、IndexedDB 或 session 原值。

如果还没有准备 Runner、Profile registry、Wechatsync adapter 和本机 loopback bridge，先看 [配置、环境与状态](configuration.md)。如果要审查完整验收链路和底层制品版本，继续看 [知乎首次设置与草稿验收](zhihu-first-run.md)。

## 这条路径会做什么

<div class="grid cards" markdown>

- **登录**

    `login` 内部先做只读 auth 检查。已登录时直接返回 `READY`，不会打开二维码页；未登录时才从当前登录页的 page-owned `login_url` 生成 QR。

- **预检文章**

    `draft --dry-run` 只解析 source 并返回 preview，不启动浏览器、不连接扩展、不写知乎。

- **发送 review 草稿**

    不带 `--dry-run` 的 `draft` 调用一次 Wechatsync create 路径，写 `0600` receipt，并返回知乎 `/edit` review URL。

- **明确边界**

    ChatPost 当前只创建 review 草稿，不做最终发布，不做 same-ID update；`RESULT_UNKNOWN` 后不能自动重试。

</div>

## 0. 设定本次运行变量

```bash
CHATPOST=chatpost
REGISTRY=/absolute/path/to/accounts.toml
PROFILE=zhihu-personal
SOURCE=/absolute/path/to/article.md
RUN_DIR="$HOME/.chatarch/chatpost/runs/quickstart-$(date +%Y%m%d-%H%M%S)"
install -d -m 700 "$RUN_DIR"
```

`accounts.toml` 只保存非敏感 Profile metadata，例如 alias、platform、runner_config、profile 和 label。不要把 Cookie、LocalStorage、二维码 payload、验证码、手机号、密码、bridge token 或 WebSocket UUID 写入 registry、文章、receipt、日志或文档。

## 1. 确认可见 CLI 和 Profile

```bash
"$CHATPOST" --tree

"$CHATPOST" platforms \
  --output json \
  -I

"$CHATPOST" profiles \
  --platform zhihu \
  --registry "$REGISTRY" \
  --output json \
  -I
```

确认输出中能看到 `PROFILE` 对应的知乎 target。这里仍然只是 registry 只读发现，不会读取浏览器登录态。

## 2. 登录或复用已登录 Profile

先做一次只读状态检查：

```bash
"$CHATPOST" zhihu status "$PROFILE" \
  --registry "$REGISTRY" \
  --output json \
  -I
```

然后运行登录入口：

```bash
"$CHATPOST" zhihu login "$PROFILE" \
  --registry "$REGISTRY" \
  --qr "$RUN_DIR/zhihu-login.png" \
  --receipt "$RUN_DIR/zhihu-login-receipt.json" \
  --timeout 900 \
  --output json \
  -I
```

行为约定：

- 如果 `PROFILE` 已登录，`login` 直接返回 `READY`，不会生成 QR，也不会要求扫码。
- 如果未登录，`login` 打开同一个 Profile 的知乎登录页；只有拿到该页面正在轮询的 page-owned `login_url` 后，才用它生成 QR 图片和 receipt。
- 页面截图不是登录 handoff。截图只能作为内部调试证据，不作为 ChatPost 的最终交付物。
- 机器验证、滑块、手机号和验证码都属于人工浏览器流程；ChatPost 不提供 `--phone`、`--code`、`--otp` 或 `--sms-code` 参数。

登录完成后再回读一次状态：

```bash
"$CHATPOST" zhihu status "$PROFILE" \
  --registry "$REGISTRY" \
  --output json \
  -I
```

继续前应看到 `READY`。

## 3. Dry-run 文章

```bash
"$CHATPOST" zhihu draft "$PROFILE" "$SOURCE" \
  --registry "$REGISTRY" \
  --dry-run \
  --output json \
  -I
```

检查 JSON 里的 `preview`、标题、正文和图片引用。`--dry-run` 是 `draft` 的参数，不是独立子命令；它不会启动浏览器、不会连接扩展、不会写知乎。

## 4. 发送到知乎 review 草稿

```bash
DRAFT_RECEIPT="$RUN_DIR/zhihu-draft-receipt.json"

"$CHATPOST" zhihu draft "$PROFILE" "$SOURCE" \
  --registry "$REGISTRY" \
  --receipt "$DRAFT_RECEIPT" \
  --output json \
  -I
```

成功时应看到：

- `status` 为 `DRAFT_CREATED`；
- 有知乎 draft ID；
- 有 `/edit` review URL；
- `$DRAFT_RECEIPT` 已写入，权限为 `0600`。

这一步只创建 review 草稿，不点击最终发布。打开 review URL 后仍需要人工检查标题、正文、图片和排版。

## 5. 收尾或退出登录

如果要保留该 Profile 供后续草稿复用，可以不登出。需要清理登录态时运行：

```bash
"$CHATPOST" zhihu logout "$PROFILE" \
  --registry "$REGISTRY" \
  --output json \
  -I
```

`logout` 也会先做只读 auth：未登录时直接 no-op；已登录时才清理知乎 origin 登录态。它不读取或导出 session 值。

## 常见停点

| 停点 | 处理 |
| --- | --- |
| `login` 已返回 `READY` 但没有 QR | 这是预期行为，说明 Profile 已登录。 |
| 登录页需要滑块或验证码 | 停在人工浏览器流程，不把验证码写进 CLI 参数或日志。 |
| 没有 page-owned `login_url` | 登录 handoff 失败；不要用页面截图冒充 QR 结果。 |
| `draft --dry-run` preview 不对 | 修 source 后重新 dry-run；不会写知乎。 |
| `draft` 返回 `RESULT_UNKNOWN` | 不自动重试；读取 receipt 和日志，人工确认知乎后台状态。 |
| 想最终发布 | 当前 ChatPost 没有最终发布命令；review 后由人工在知乎完成。 |
