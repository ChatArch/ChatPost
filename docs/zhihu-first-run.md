# 知乎首次设置与草稿验收

本页是 `ChatPost 0.1.0` 的可执行 Quick Start。它复刻已验证的 Playwright-cache + Profile + Wechatsync 路线，并把制品与任务责任拆到 ChatUp/ChatPost。

## 最终边界

```text
ChatUp 0.2.4
  -> 安装 exact Playwright package + browser revision
  -> chatup.playwright.resolve(...)

ChatPost 0.1.0
  -> 持久 Profile + 浏览器生命周期
  -> exact extension + loopback CDP/bridge
  -> 登录 checkpoint / auth / dry-run / 单次 create / receipt

Wechatsync
  -> 知乎 adapter 与草稿写入
```

这条链路：

- user-level；
- 不需要 Docker 或 root；
- 不读取或导出 Cookie/LocalStorage；
- 只创建草稿，不点击最终发布；
- `RESULT_UNKNOWN` 后禁止自动重试；
- 尚不支持 same-ID update。

## 1. 安装 Python 包

```bash
python3 -m venv "$HOME/.chatarch/venvs/chatpost"
"$HOME/.chatarch/venvs/chatpost/bin/python" -m pip install --upgrade pip
"$HOME/.chatarch/venvs/chatpost/bin/python" -m pip install \
  "chatup==0.2.4" \
  "chatpost==0.1.0"

CHATUP="$HOME/.chatarch/venvs/chatpost/bin/chatup"
CHATPOST="$HOME/.chatarch/venvs/chatpost/bin/chatpost"
"$CHATUP" --version
"$CHATPOST" --version
```

## 2. 准备 Node.js 与 Playwright browser

```bash
"$CHATUP" nodejs -I
# 按 ChatUp 输出刷新当前 shell 后确认 node/npm 可用。
node --version
npm --version

"$CHATUP" playwright install 1.61.1 \
  --browser chromium \
  --output json \
  -I

"$CHATUP" playwright doctor 1.61.1 \
  --browser chromium \
  --output json \
  -I
```

ChatUp 将 package 与 browser 安装到 `~/.chatarch/playwright/1.61.1/`。ChatPost 只解析该安装，不隐式下载或升级。

当前任务实测组合：

```text
Playwright package  1.61.1
browser             chromium
revision            1228
Chrome for Testing  149.0.7827.55
```

## 3. 准备 Wechatsync adapter

当前打通版本来自 ChatArch 的知乎草稿 CLI 分支：

```bash
git clone https://github.com/ChatArch/Wechatsync.git "$HOME/.chatarch/src/Wechatsync"
cd "$HOME/.chatarch/src/Wechatsync"
git checkout 0073787cfbff0f7af4d1b427da3adbb16d92eeb8
corepack enable
pnpm install --frozen-lockfile
pnpm build

test -f packages/cli/dist/index.js
test -f packages/extension/dist/manifest.json
```

ChatPost 不复制 Wechatsync 的知乎业务逻辑，只编排其 CLI、扩展和回执。

## 4. 创建 Profile 与私密 bridge env

```bash
RUNNER_HOME="$HOME/.chatarch/chatpost/runners/zhihu-primary"
install -d -m 700 "$RUNNER_HOME/profile"
install -d -m 700 "$RUNNER_HOME/run"
```

生成本地 bridge token，不在终端输出：

```bash
RUNNER_HOME="$RUNNER_HOME" python3 - <<'PY'
import os
import secrets
from pathlib import Path

path = Path(os.environ["RUNNER_HOME"]) / "bridge.env"
path.write_text(
    "WECHATSYNC_TOKEN=" + secrets.token_urlsafe(32) + "\n",
    encoding="utf-8",
)
path.chmod(0o600)
PY
```

bridge token 只鉴权本机扩展与 CLI，不是知乎密码。不要把 env、Profile、Cookie、LocalStorage、二维码或验证码加入 Git、文档或日志。

## 5. 写 Runner TOML

从仓库示例复制：

```bash
cp examples/zhihu/runner.toml.example "$RUNNER_HOME/runner.toml"
chmod 600 "$RUNNER_HOME/runner.toml"
```

把示例中的路径改成当前机器的绝对路径。核心字段：

```toml
[zhihu]
playwright_version = "1.61.1"
playwright_home = "/home/user/.chatarch/playwright"
profile_dir = "/home/user/.chatarch/chatpost/runners/zhihu-primary/profile"
extension_dir = "/home/user/.chatarch/src/Wechatsync/packages/extension/dist"
node_bin = "/absolute/path/to/node"
wechatsync_cli = "/home/user/.chatarch/src/Wechatsync/packages/cli/dist/index.js"
env_file = "/home/user/.chatarch/chatpost/runners/zhihu-primary/bridge.env"
cdp_host = "127.0.0.1"
cdp_port = 9227
bridge_host = "127.0.0.1"
bridge_port = 9527
extension_id = "dipgimoobbhdefncjomgehikkbaklgii"
headless = true
browser_args = ["--disable-dev-shm-usage"]
```

macOS 通常可把 `browser_args` 设为空数组。Linux 是否需要额外参数应以该机器真实 Chrome smoke 为准；不要默认公开端口或关闭安全边界。

## 6. 运行静态 preflight

```bash
"$CHATPOST" zhihu preflight \
  --config "$RUNNER_HOME/runner.toml" \
  --output json \
  -I
```

只有 `status=READY` 才继续。它会验证：

- exact ChatUp Playwright installation；
- Profile 存在且不向 group/other 开放；
- Node、Wechatsync CLI 与扩展 manifest；
- env 权限和 token 是否存在，但不显示值；
- CDP/bridge 均显式绑定数值 IPv4 loopback `127.0.0.1` 且端口尚未被占用；拒绝 `localhost` 和 IPv6 loopback，避免连接 readiness 与 listener PID ownership 命中不同 socket。

## 7. 首次人工登录

已有登录 Profile 可先做一次只读检查：

```bash
"$CHATPOST" zhihu auth \
  --config "$RUNNER_HOME/runner.toml" \
  --output json \
  -I
```

若未登录，启动登录 checkpoint：

```bash
"$CHATPOST" zhihu login \
  --config "$RUNNER_HOME/runner.toml" \
  --timeout 900 \
  --output json \
  -I
```

`login` 保持同一浏览器/Profile，打开知乎登录页，并循环执行只读 auth；扫码或验证码成功后返回 `READY`。有桌面的机器可设置 `headless=false`。服务器必须使用经过授权的本机显示/隧道或受控截图流程；不得把 CDP、VNC 或 bridge 暴露到公网。

登录后再运行一次 `auth`，确认同一 Profile 可复用。ChatPost 不读取 Profile 内的 Cookie。

## 8. Dry-run

```bash
ARTICLE=/absolute/path/to/article.md
"$CHATPOST" zhihu draft dry-run "$ARTICLE" \
  --config "$RUNNER_HOME/runner.toml" \
  --output json \
  -I
```

从 JSON 的 `preview` 字段确认标题、正文、图片引用和固定 marker 正确。preview 最多返回 8000 个字符，并已按私有 env 中的值脱敏。dry-run 不启动浏览器、不连接扩展、不写知乎。

## 9. 只创建一次草稿

```bash
RECEIPT="$RUNNER_HOME/run/zhihu-draft-receipt.json"
"$CHATPOST" zhihu draft create "$ARTICLE" \
  --config "$RUNNER_HOME/runner.toml" \
  --receipt "$RECEIPT" \
  --output json \
  -I
```

成功条件：

- `status=DRAFT_CREATED`；
- 有知乎 draft ID 与 `/edit` review URL；
- receipt 权限为 `0600`；
- 打开编辑页能回读期望标题和 marker；
- 停在草稿箱，未最终发布。

每次 browser 启动都会生成随机 `data:text/plain,chatpost-run-*` marker。ChatPost 只有在配置的 loopback 端口同时看到该 marker 和对应 browser WebSocket UUID 后，才把 CDP 绑定为本次进程所有。

扩展发现、`Target.attachToTarget`、扩展求值和登录页创建全部通过这个已捕获的 browser WebSocket 完成。`Target.createTarget` 返回本轮 popup ID；ChatPost 将这个 exact identity 贯穿 browser session，并在 attach 前重验其精确 popup URL 和 `page` / `background_page` 类型。恢复出来的旧 popup、其他 stale popup 和 service worker 均不会被选择，也不会跟随后来从可复用 CDP 端口发现的 target-level WebSocket。只有 loopback bridge 的 listener PID（由监听 socket 反查）属于本次启动的 Node 子进程时才判定 ready；foreign listener 或 Wechatsync secondary mode 会在唤醒扩展前 fail closed。create 在这条歧义路径上返回 `RESULT_UNKNOWN`，不得自动重试。

正常清理通过启动时捕获的 browser WebSocket endpoint 发送 CDP `Browser.close`，不会重新发现后来可能占用同一端口的其他浏览器，也不会发送进程终止信号。若草稿结果已经明确、但清理失败，receipt 仍保留 `DRAFT_CREATED`，并附带 `cleanup_status=MANUAL_RECOVERY_REQUIRED`；此时人工恢复进程，不能再次执行 create。browser 启动失败时，ChatPost 会先等待 stderr drain，再返回限长诊断；Profile 路径、私密赋值、URL/连接信息和运行 marker 均经过脱敏。若私有 env 在 preflight 后消失、不可读或不再包含预期 token，diagnostics 会 fail-closed 为 `[REDACTED]`，外围错误仍保留 browser 退出码。

receipt 分别记录 browser `cleanup_status`、本轮 popup `extension_cleanup_status` 与 adapter `adapter_cleanup_status`；只有需要人工恢复时才写对应 error 字段。该契约同时适用于 `DRAFT_CREATED` 与 `RESULT_UNKNOWN`，包括 adapter 非零退出、成功退出但缺 review URL、扩展唤醒失败、adapter 超时和唤醒后的输出读取失败。cleanup 会通过 browser-level `Target.closeTarget` 重验并只关闭本轮创建的 popup，然后请求 `Browser.close`；popup cleanup 失败会被独立记录，不会阻止 browser close 尝试，也不会覆盖 authoritative result。若本轮 adapter 子进程在一次有界停止请求后仍未退出，create 仍保持 `RESULT_UNKNOWN`，记录 `adapter_cleanup_status=MANUAL_RECOVERY_REQUIRED`，保留主结果和子进程供人工恢复，并单独报告 adapter cleanup error。`source_sha256 在 browser 或 adapter 启动前捕获`；成功或歧义 receipt 均复用该值，因此后续 source 文件被修改、删除或无法读取都不会覆盖 authoritative result。receipt 不写入 target ID、browser endpoint、token 或连接信息。

如果 authoritative result 已经产生但 receipt 无法落盘，ChatPost 不会用普通文件系统异常覆盖主结果：明确成功时先输出 `DRAFT_CREATED`；歧义写入时继续明确 `RESULT_UNKNOWN`；随后报告 receipt 无法写入，并明确不得自动重试。

adapter stdout/stderr 除了替换私有 env 的精确值，还会结构化遮蔽动态私密赋值，包括跨行结构化私密赋值中的嵌套 object/array 与跨行 quoted value；若无法证明私密值的闭合边界，则丢弃其后的未知文本，只恢复用于 authoritative result 的严格知乎 `/edit` review URL 白名单。WebSocket URL、loopback 连接信息和 ownership marker 也会被遮蔽。

图片上传失败可以与草稿创建成功同时发生；必须按编辑页实际内容报告，不能把 CLI exit 0 当成图片完整证明。

## 10. 歧义恢复

若 receipt 为：

```json
{"status": "RESULT_UNKNOWN"}
```

立即停止自动化：

1. 不重新运行 `draft create`；
2. 在同一知乎账号草稿箱按标题、marker 与时间查找；
3. 找到后补录唯一 draft ID/review URL；
4. 确认不存在后也要人工决定是否重新创建。

## 两仓协作结论

- ChatUp 只向上提供 Playwright package/browser substrate；不创建 Profile、不启动浏览器、不懂知乎。
- ChatPost 面向任务管理 Profile、进程、CDP、bridge、登录 checkpoint、单次写入和 receipt；不复制 Playwright 下载逻辑，也不读取登录数据库。
- Wechatsync 是知乎 adapter；其协议变化应在 ChatPost adapter 边界显式兼容。
- 文章 update 必须基于已保存的 draft/article ID 另开验收，不能用标题匹配或再次 create 冒充 update。
