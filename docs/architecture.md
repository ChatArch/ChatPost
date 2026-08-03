# 总体架构设计

!!! warning "状态：设计提案"
    `ChatPost 0.1.0` 已实现 task-specific `zhihu preflight/auth/draft` 链路；本页的通用 Runner、Account、Publication 与 update 资源模型仍是提案。

## 一句话模型

ChatPost 是控制面；ChatUp 提供可复用的 Playwright package/browser 环境；带持久浏览器 Profile 的 Browser Runner 是执行面；平台账号只是绑定到 Runner 的逻辑发布目标。

```text
Markdown + local assets
        |
        v
ChatPost control plane
  parse -> plan -> policy -> ledger
        |
        | bridge task + receipt
        v
Browser Runner
  Chrome for Testing
  + isolated user-data-dir
  + adapter extension
        |
        v
Platform session in browser
  -> create/update draft
  -> human review
  -> human final publish
```

ChatPost 不读取平台 Cookie，也不把浏览器 Profile 当作普通配置文件管理。

## 已验证事实与提案

| 层级 | 当前状态 | 说明 |
|---|---|---|
| Markdown 到知乎草稿 | 已验证 | 现有 Wechatsync 实践已创建并回读知乎草稿，未点击最终发布。 |
| Chrome for Testing host binary | 已验证 | 成功链路直接运行本地二进制，没有使用 Docker。 |
| 独立持久化 Profile | 已验证 | 知乎登录态保留在专用 `user-data-dir`，未导出 Cookie。 |
| 知乎二维码扫码登录 | 已验证 | 在可见隔离浏览器中完成扫码，Profile 随后保持登录态。 |
| 知乎短信验证码登录 | 待单独验收 | 这是标准人工备选路径，但现有端到端证据不应宣称它已经走通。 |
| loopback bridge + token | 已验证 | 扩展与 CLI 通过本机 WebSocket 通讯，Token 不是知乎凭据。 |
| ChatUp Playwright environment | 已发布依赖 | `chatup 0.2.4` 提供 `chatup playwright` 与 `chatup.playwright.resolve`；ChatPost 不重复实现下载。 |
| ChatPost task-specific Zhihu Runner | 已实现 | `preflight/auth/draft`、持久 Profile、exact extension、loopback CDP/bridge 与 receipt 已有代码和测试。 |
| 通用 runner/account CLI | 提案 | 通用 registry、命令和 schema 尚未实现。 |
| 多账号调度与 publication ledger | 提案 | 本页定义资源和状态边界，后续按测试实现。 |

## 核心资源

### ChatUp Playwright dependency

Playwright package 与其声明的 browser revision 是 ChatUp 管理的机器级安装，不是 ChatPost Resource。ChatPost 只声明兼容版本并解析一个只读 descriptor：

```text
ChatUp PlaywrightBrowserInstallation
├── kind = playwright
├── playwright_version
├── browser / browser_revision / browser_version
├── binary_path
├── root_dir = installation root
└── package_dir / browsers_dir / node_version
```

`chatup playwright install <tested-version> --browser chromium` 安装到 `~/.chatarch/playwright/`。ChatPost 通过 `chatup.playwright.resolve(...)` 解析已有安装；缺失时 fail closed 并提示运行 ChatUp，不自行下载、解压或修改系统 Chrome。

ChromeDriver 是另一个独立 ChatUp backend（`chatup chromedriver` / `chatup.chromedriver`）。当前 ChatPost Runner 直接启动 Chrome for Testing 并使用 CDP，不消费 ChromeDriver，也不假设两个 backend 共用版本或 descriptor。

### Runner

Runner 是一个 Browser persona 的执行边界：

```text
Runner
├── one ChatUp-resolved Chrome descriptor
├── one Chrome process
├── one isolated user-data-dir
├── one CDP endpoint
├── one extension/bridge instance
├── one bridge secret reference
└── one serialized write queue
```

同一 Runner 内写任务串行；不同 Runner 在端口、目录和 token 独立时可以并行。

### Account

Account 是逻辑目标，统一写成 `platform@alias`：

```text
zhihu@personal -> runner: local-personal
zhihu@brand    -> runner: local-brand
```

Alias 不是平台用户名，不应包含手机号、邮箱或真实姓名。Account 只保存平台、Runner 绑定和最近 auth 状态。

### Publication

Publication 是一个 source 与一个 target 之间的持久映射：

```text
source identity + source hash
        <->
platform account + draft/article ID
```

它用于幂等、update、状态回查和 `RESULT_UNKNOWN` 恢复；不能用标题代替这个映射。

## 控制面与执行面

### ChatPost 控制面负责

- 解析 Markdown、front matter 和本地资源；
- 解析 `platform@alias`、Runner 和 adapter 能力；
- 生成无远端写入的 plan；
- 分配 Runner 写锁；
- 发起 create 或 fail-closed update；
- 保存 receipt、source hash、draft ID 和状态；
- 在正确 Runner 中打开草稿供人工 Review。

### Browser Runner 执行面负责

- 启动固定版本 Chrome；
- 持有浏览器 Profile 与站点登录态；
- 加载并识别正确扩展；
- 通过 bridge 接收任务；
- 使用浏览器现有会话上传图片、创建或更新草稿；
- 返回结构化回执；
- 遇到登录、验证码、风控或版本不兼容时停止并报告。

## 三个连接面

现有 Wechatsync 源码确认：浏览器扩展是 WebSocket client，bridge process 是 WebSocket server。ChatPost 控制面不应被描述成这个 WebSocket 的 client。

| 字段/transport | 示例 | 发起方 → 接收方 | 边界 |
|---|---|---|---|
| `cdp_url` | `http://127.0.0.1:9227` | Runner manager → Chrome | 启动检查、打开登录页、扩展身份验证和诊断。 |
| `bridge_ws_url` | `ws://127.0.0.1:9527` | Browser extension → bridge server | 扩展接收任务并返回回执；RPC message 使用 bridge token。 |
| `control_transport` | `stdio`；可选 `http://127.0.0.1:9528` | ChatPost adapter → bridge process | 本地默认 in-process/stdio；companion HTTP 只用于明确的进程边界。 |

对于 managed local Runner，ChatPost 自动分配端口、配置 exact extension 的 `bridge_ws_url`/token，并优先使用没有公开 listener 的 stdio 控制通道。普通用户不手填这些 URL。

远端 Runner 暴露的是独立的认证 control API，而不是把 extension WebSocket、CDP 或未鉴权 companion HTTP 直接映射到公网。

## 从安装到草稿的生命周期

```text
CHROME_DEPENDENCY_MISSING
  -> user runs chatup playwright install <tested-version> --browser chromium
CHROME_DEPENDENCY_READY
  -> runner add/start
RUNNER_STARTING
  -> process + CDP + exact extension + bridge checks
RUNNER_READY
  -> account add/login
NEEDS_LOGIN
  -> visible human login checkpoint
AUTH_CHECKING
  -> read-only adapter auth
ACCOUNT_READY
  -> plan
PLANNED
  -> explicit draft create/update
RUNNING
  -> DRAFT_CREATED -> AWAITING_REVIEW
  -> RESULT_UNKNOWN
  -> NEEDS_ACTION
```

任何可能已经到达平台但没有拿到回执的写操作都进入 `RESULT_UNKNOWN`，禁止自动重试。

## 状态所有权

| 数据 | 所有者 | 是否秘密 | 是否进入 ledger |
|---|---|---:|---:|
| Playwright package、browser revision/version 与 binary path | ChatUp `~/.chatarch/playwright/` | 否 | 否 |
| user-data-dir 路径引用 | Runner config | 否 | 否 |
| Profile 内 Cookie/Local Storage | Chrome Profile | 是 | 否 |
| bridge URL、端口 | Runner config/state | 否 | 否 |
| bridge token | ChatEnv canonical source + exact extension 自有 storage 副本 | 是 | 只存引用 |
| Account alias 与 Runner 绑定 | Account registry | 否 | 作为 target 引用 |
| source hash、draft ID、review URL | Publication ledger | 否/敏感元数据 | 是 |
| 密码、验证码、二维码内容 | 不持久化 | 是 | 否 |

详细文件和配置分层见 [配置、环境与状态](configuration.md)。

## 任务驱动的首个验收场景

仓库提供一篇固定的中文 MkDocs 入门稿：

```text
examples/zhihu/mkdocs-quickstart.md
```

它包含标题、段落、列表、表格、代码块、链接、本地 PNG 和稳定 marker `CHATPOST-MKDOCS-SMOKE-V1`。后续实现以这一个任务作为端到端验收：

1. 使用隔离的已授权知乎 Runner；
2. auth 与 plan 必须先成功；
3. 只允许一次明确的 `draft create`；
4. 回读返回的草稿 ID、标题、marker、代码和图片；
5. 写入 ledger；
6. 停在人工 Review，不点击最终发布。

流程详见 [知乎首次设置与草稿验收](zhihu-first-run.md)。

## 首个功能版本范围

首个功能版本包含：

- 对已发布 `chatup>=0.2.4,<0.3.0` 的有界依赖，以及只读 Chrome descriptor 解析；
- host Runner 生命周期与健康检查；
- 一个 Runner 一个独立 user-data-dir；
- ChatEnv bridge secret reference；
- Account 注册、人工登录 checkpoint 和只读 auth；
- plan、明确 draft create、fail-closed draft update；
- publication ledger、open、status 和 reconcile；
- 知乎 adapter 首先落地。

后续能力包括 Docker/remote Runner、动态 broker、多平台 adapter、强租户隔离和经单独授权的发布能力。

## 安全边界

- 不读取、导出或传输平台 Cookie；
- 不接收平台密码或一次性验证码；
- 不复用日常 Chrome Profile；
- 不让两个 Runner 共享 user-data-dir；
- 不公开 CDP、bridge 或 companion HTTP；
- 不把 create 与 update 合并成有隐式回退的 `sync`；
- 不自动点击最终 Publish。
