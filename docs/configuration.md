# 配置、环境与状态设计

!!! warning "状态：设计提案"
    `ChatPost 0.1.0` 已读取 task-specific `[zhihu]` Runner TOML 和权限 `0600` 的 bridge env 文件；本页其余通用 Runner/Account/ledger schema 仍是提案。

## 设计结论

ChatPost 不应该把所有内容塞进 `.env`。配置分成四类：

1. **机器依赖与版本化制品**：Playwright package/browser 由 ChatUp 管理，扩展由 ChatPost/adapter 管理；
2. **非秘密配置**：Runner、Account、端口策略和路径引用；
3. **秘密**：每个 bridge/远端 Runner 的 token，放 ChatEnv；
4. **运行状态与业务台账**：进程健康状态和 publication ledger，分别持久化。

Cookie、Local Storage、密码和验证码不属于任何 ChatPost 配置层。

## 文件布局

### 用户级 ChatArch Home

```text
~/.chatarch/
├── playwright/                   # ChatUp-owned Playwright backend
│   └── <playwright-version>/{package,browsers,installation.json}
└── chatpost/
    ├── config.toml
    ├── extensions/
    │   └── wechatsync/<version>/...
    ├── runners/
    │   └── <runner>/
    │       ├── runner.toml
    │       ├── chrome-data/      # mode 0700，包含浏览器登录态
    │       ├── state.json        # 非秘密 runtime state
    │       ├── run/
    │       └── logs/
    ├── accounts.toml
    └── logs/
```

### 内容 workspace

```text
<workspace>/.chatpost/
├── config.toml                   # source/target 默认值，可选
└── publications.sqlite3          # source-to-target ledger
```

Chrome installation 是 ChatUp 机器级资源；Profile 是 ChatPost Runner 状态；文章映射是 workspace 级状态。三者分开，避免把可移动内容仓库与某台机器或登录态绑定。

当前已实现的登录基础层默认使用 `~/.chatarch/chatpost/` 作为 ChatArch-owned state root：`CHATPOST_HOME` 可覆盖 state root，`CHATPOST_ACCOUNT_REGISTRY` 或 CLI `--registry PATH` 可覆盖 registry 文件；默认 registry 是 `~/.chatarch/chatpost/accounts.toml`。普通用户不需要在仓库根目录、当前工作目录或临时 project 目录放 `accounts.toml`。

## ChatUp Playwright dependency

ChatPost 通过已发布的有界依赖消费 ChatUp 与 ChatBrowser：

```toml
dependencies = ["chatup>=0.2.4,<0.3.0", "chatbrowser>=0.1.2,<0.2.0"]
```

环境准备由 ChatUp 独立完成：

```bash
chatup playwright install <chatpost-tested-version> --browser chromium --output json -I
```

ChatPost 启动 Runner 时只调用 `chatup.playwright.resolve(...)`：读取 Playwright version、browser revision/version、binary path、package/browser roots 与 Node version。它不调用安装 API，不保存另一份 browser registry，也不下载浏览器。descriptor 缺失或版本不兼容时 fail closed，并提示运行 `chatup playwright install <chatpost-tested-version> --browser chromium`。

## 非秘密配置示例

当前可读的 task-specific TOML 见 [CLI 树](cli-tree.md)；以下通用 registry TOML 仍是预期 schema：

```toml
schema_version = 1

[runners.zhihu-personal]
runtime = "host"
visible = true
profile_mode = "managed"
attach_existing_cdp = false

[runners.zhihu-personal.cdp]
bind = "127.0.0.1"
port = "auto"

[runners.zhihu-personal.bridge]
mode = "managed"
ws_bind = "127.0.0.1"
ws_port = "auto"
control_transport = "stdio"
token_profile = "zhihu-personal"

[accounts."zhihu@personal"]
platform = "zhihu"
runner = "zhihu-personal"
```

`attach_existing_cdp = false` 是默认值：ChatPost 启动并拥有一个 browser process，结束时通过启动时捕获的 browser CDP endpoint 关闭它。如果一个已知 browser 已经持有该 Profile 且暴露 loopback CDP，可设置 `attach_existing_cdp = true` 并让 `cdp_port` 指向现有 endpoint。attach 模式只创建/关闭本次 extension popup，保留现有 browser 运行，并在 receipt 中记录 `cleanup_status=LEFT_RUNNING_EXISTING_CDP`。

## ChatEnv 只存秘密

每个 Runner 使用独立 ChatEnv profile。首版需要的生产字段：

| 字段 | 类型 | 用途 |
|---|---|---|
| `CHATPOST_BRIDGE_TOKEN` | sensitive | ChatPost CLI 与该 Runner 扩展 bridge 的控制通道鉴权。 |
| `CHATPOST_REMOTE_RUNNER_TOKEN` | sensitive / later | 未来远端 Runner 的注册或 transport 鉴权。 |

当前脚手架的 `CHATPOST_API_KEY` 不代表知乎或 bridge 凭据；实现时应删除或替换这个没有业务语义的占位字段。

Runner 非秘密配置只保存 profile 名称，例如：

```toml
[runners.zhihu-personal.bridge]
token_profile = "zhihu-personal"
```

ChatEnv 是 token 的 canonical source。为了让扩展验证 RPC，Runner 在证明 exact extension identity 后，把同一个 runner-scoped token 写入该扩展自己的 `chrome.storage.local`。这个 Profile 内副本仍是秘密，但不是知乎 Cookie；轮换必须同时更新 ChatEnv 和扩展副本，任何一侧失败都让 Runner 退出 READY。

这是 ChatPost 的新 ownership 提案，不是对旧实践的描述。已验证原型由扩展生成随机 token，再由受控脚本把同一值写入权限 `0600` 的 `.env`。正式实现如果改为 ChatEnv 生成/托管 canonical value，必须增加原子 provision/rotation 测试；不能假设现有扩展已经支持这个方向。

读取优先级遵循 ChatArch 约定：

```text
显式 CLI/Python 参数
  > 显式 -e/--env-profile
  > 当前 ChatEnv profile
  > 非秘密配置默认值
```

`config show` 只能显示 profile 名称、key 名称和是否已配置，不能显示 token 值或掩码尾部。

## URL 与端口

### Managed local Runner

用户不应填写 URL。ChatPost 分配端口并在启动后派生：

```text
cdp_url       = http://127.0.0.1:<debug-port>
bridge_ws_url = ws://127.0.0.1:<bridge-port>
control       = stdio
```

- `cdp_url` 只给 Runner manager；
- `bridge_ws_url` 写入 exact extension 配置，由扩展主动连接 bridge server；
- ChatPost adapter 默认通过 in-process/stdio 调用 bridge process；
- 如果需要 companion HTTP，它使用单独端口并同时满足 loopback 与 control authentication，不能只依赖“在本机”；
- 端口租约写 runtime state，不写 publication ledger。

Runner 配置扩展时只能写 bridge URL、token 和 enable flag 这些扩展自有字段。实现必须先证明 exact extension identity，不能读取或修改知乎页面的 Cookie/Local Storage。无法安全自动配置时，Runner 进入 `NEEDS_EXTENSION_SETUP` 并打开扩展设置页让用户处理。

### Adopt existing Profile

为了迁移已经登录的 Profile，Runner 可以按引用接管：

```text
profile_mode = adopt
user_data_dir = <existing path>
```

ChatPost 不复制、不压缩、不检查 Cookie 内容。第一次 start 前必须确认该目录未被其他 Chrome 进程占用，并把目录权限与所有权纳入 doctor。

### External Runner

未来外部 Runner 暴露独立 control API，而不是 extension WebSocket：

```toml
[runners.remote-brand.control]
transport = "https"
url = "https://runner.example.invalid/v1"
token_profile = "remote-brand"
```

外部 control URL 必须使用受控 tunnel/VPN 或 TLS+认证；不能把本地 extension WebSocket、CDP 或 companion HTTP 直接映射到公网。

## Runtime state

`runners/<name>/state.json` 只保存可重建、非秘密状态：

```json
{
  "state": "READY",
  "pid": 12345,
  "chrome_provider": "chatup",
  "chrome_ref": "chrome-for-testing@<resolved-version>",
  "chrome_binary_path": "<resolved-path>",
  "cdp_port": 9227,
  "bridge_port": 9527,
  "control_transport": "stdio",
  "extension_id": "<verified-id>",
  "extension_protocol": "<version>",
  "started_at": "<timestamp>",
  "last_heartbeat_at": "<timestamp>"
}
```

PID 不能单独证明身份。`runner stop` 还必须匹配 user-data-dir、binary、Runner owner marker 或服务单元。

当前 Wechatsync request/response message schema 没有协商 protocol version。`extension_protocol` 是 ChatPost 的待实现门禁：可以通过显式 handshake，或由 compatibility manifest 证明 exact bridge/extension artifact pair。在两者都没有之前必须报告 `PROTOCOL_UNVERIFIED`，不能伪报版本兼容。

## Account registry

当前已实现的 `accounts.toml` 保存非秘密 Profile metadata 和 runner config 引用；默认位置是 `~/.chatarch/chatpost/accounts.toml`：

```toml
[accounts."zhihu-personal"]
platform = "zhihu"
runner_config = "runners/zhihu-personal/runner.toml"
profile = "zhihu-personal"
label = "Personal Zhihu browser Profile"
login_methods = ["qr"]

[accounts."xhs-personal"]
platform = "xiaohongshu"
runner_config = "runners/xhs-personal/runner.toml"
profile = "xhs-personal"
label = "Personal Xiaohongshu browser Profile"
login_methods = ["qr"]
```

相对 `runner_config` 路径按 registry 所在目录解析，因此默认会落在 `~/.chatarch/chatpost/runners/...`。它不保存用户名、手机号、密码、Cookie、LocalStorage、IndexedDB、session、token 或验证码。平台返回的公开 display name 只能作为诊断结果，不应成为目标主键。

## Publication ledger

建议首版使用 SQLite，至少包含：

```text
source_ref
source_sha256
target                 # platform@alias
runner
operation              # create_draft / update_draft
draft_id / article_id
review_url / public_url
adapter_version
browser_version
extension_protocol
status
receipt_json_redacted
created_at / updated_at
```

唯一约束应等价于：

```text
UNIQUE(workspace, source_ref, target)
```

Token、Cookie、请求头、Profile 内容和一次性登录材料永远不进入 ledger。

## 配置优先级

```text
command options
  > workspace .chatpost/config.toml
  > user ~/.chatarch/chatpost/config.toml
  > built-in safe defaults
```

秘密不参与这个普通配置合并，而是通过明确的 ChatEnv profile 解析。这样 `config validate` 可以在不读取秘密值的情况下检查引用是否存在。

## 旧 Wechatsync 实践迁移表

| 旧字段/状态 | ChatPost 资源 |
|---|---|
| `WECHATSYNC_CHROME_BIN` | ChatUp `PlaywrightBrowserInstallation.binary_path`；Runner 启动时只读解析。 |
| `WECHATSYNC_CHROME_PROFILE` | Runner `user_data_dir`；默认 managed，也可 adopt 现有目录。 |
| `WECHATSYNC_DEBUG_PORT` | Runner CDP lease；默认 auto。 |
| extension `serverUrl` / `SYNC_WS_PORT` | Runner `bridge_ws_url` / WebSocket port lease；扩展主动连接。 |
| `SYNC_HTTP_PORT` | 可选 companion control endpoint；ChatPost managed local 默认改用 stdio。 |
| `WECHATSYNC_TOKEN` | Runner 对应 ChatEnv profile 的 `CHATPOST_BRIDGE_TOKEN`。 |
| `.env` 中的登录辅助信息 | 不迁移；平台登录由可见浏览器人工完成。 |
| `state/publication-state.json` | workspace publication ledger。 |

迁移不是复制 `.env` 或 Profile。它是先由 ChatUp 提供 Chrome dependency，再建立 Runner、Account 和 Publication 三种 ChatPost 资源的映射。

## 权限与备份

- `chrome-data/`：目录权限 `0700`；不自动备份、不进入 Git。
- ChatEnv secret profile：由 ChatEnv 负责文件权限、写入和脱敏。
- `state.json`：不含秘密；写入采用原子替换。
- `publications.sqlite3`：包含草稿 URL/ID 等敏感元数据，应按用户数据保护。
- logs：默认过滤 URL query、headers、Cookie、Token 和二维码内容。

## Schema 验证

提案中的 `config validate` / `doctor` 至少检查：

1. 已安装 `chatup>=0.2.4,<0.3.0` 和 `chatbrowser>=0.1.2,<0.2.0`，且 ChatPost 兼容版本可由 `chatup.playwright.resolve` 解析并执行；验证过程不触发安装；
2. Runner 名称、Profile 路径和端口租约唯一；
3. CDP/bridge bind address 为 loopback，本地 control transport 默认 stdio；
4. token profile 引用存在但不读取/打印值；
5. Account 指向存在的 Runner 和 adapter；
6. 同一 user-data-dir 没有被两个 Runner 引用；
7. workspace ledger schema 可迁移且未损坏。
