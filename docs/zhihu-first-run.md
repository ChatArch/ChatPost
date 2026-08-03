# 知乎首次设置与草稿验收

!!! warning "状态：任务导向的设计提案"
    `ChatPost 0.0.2` 尚未实现本页命令。固定博客稿和验收边界已经加入仓库，后续实现必须先通过代码/测试，再把本页升级为可执行教程。

## 目标任务

使用一个隔离的知乎账号 Runner，把下面这篇文章写入知乎草稿：

```text
examples/zhihu/mkdocs-quickstart.md
```

验收停在草稿：回读标题、marker、代码块和本地图片，写入 publication ledger，然后由用户人工 Review。ChatPost 不点击最终发布。

## 已验证基线

现有 Wechatsync 实践已经证明：

- Chrome for Testing 可以直接作为 host binary 运行，不需要 Docker；
- 可见 Chrome 能加载 unpacked 扩展；
- 知乎二维码扫码登录已在可见隔离浏览器中走通，登录态保留在独立 `user-data-dir`；
- 手机短信验证码是标准人工备选路径，但尚未在这条端到端链路中单独验收；
- bridge 通过 loopback WebSocket 与 CLI 通讯；
- CLI 可先只读验证 auth，再创建并回读草稿；
- Cookie 不需要也不应该导出给 CLI。

ChatUp 把 Chrome 二进制提升为可复用机器依赖；ChatPost 把其余脚本和状态提升为 Runner、Account 和 Publication 三种稳定资源。

## 预期首次运行

### 1. 初始化控制面

```bash
chatpost init
chatpost config validate
```

预期创建用户级配置和 workspace `.chatpost/` ledger，不创建平台草稿。

### 2. 使用 ChatUp 准备 Chrome dependency

```bash
chatup chrome-for-testing install \
  --version <chatpost-tested-version> \
  --output json \
  --doctor \
  -I
```

预期：

- ChatUp 把 Chrome for Testing 安装到 `~/.chatarch/chrome-for-testing/`；
- ChatUp 的 `installation.json` 记录 exact version、platform、binary path、来源和 digest；
- 不修改系统 Chrome；
- 不要求 Docker；
- ChatPost 后续只调用 `chatup.chrome_for_testing.resolve(...)`，不下载或升级 Chrome。

### 3. 创建隔离 Runner

```bash
chatpost runner add zhihu-personal \
  --runtime host

chatpost runner start zhihu-personal --visible
chatpost runner status zhihu-personal
```

默认创建：

```text
~/.chatarch/chatpost/runners/zhihu-personal/chrome-data/
```

`status` 必须分别报告：

```text
chrome        CHATUP_RESOLVED + exact version
process       READY
cdp           READY
extension     READY + exact identity
bridge_ws     EXTENSION_CONNECTED + protocol version
control       READY + stdio
profile       LOCKED_BY_THIS_RUNNER
```

任一项不明确时，Runner 不能进入可写状态。

当前 Wechatsync message schema 尚未协商 protocol version。因此这里的“protocol version”是实现要求，不是现有能力：首版必须新增 handshake，或使用 compatibility manifest 证明 exact bridge/extension artifact pair；否则状态为 `PROTOCOL_UNVERIFIED`，禁止真实写入。

### 4. 注册逻辑账号

```bash
chatpost account add zhihu@personal --runner zhihu-personal
chatpost account show zhihu@personal
```

这个命令只建立映射，不接收知乎密码、手机号、Cookie 或验证码。

### 5. 人工首次登录

```bash
chatpost account login zhihu@personal
```

登录路线必须分开记录：

| 路线 | 当前证据 |
|---|---|
| 图片二维码扫码 | 已验证；作为首个真实验收默认路线。 |
| 手机短信验证码 | 标准人工备选；尚未单独做端到端验收。 |

预期行为：

1. 启动或唤醒正确 Runner；
2. 打开知乎官方登录页；
3. 保持可见浏览器；
4. 用户自行完成所选人工路线；首个验收使用已验证的二维码扫码；
5. ChatPost 等待页面离开登录状态；
6. adapter 执行只读 auth check；
7. Account 状态更新为 `READY`。

登录超时、二维码过期、验证码或风控都进入 `NEEDS_LOGIN` / `NEEDS_ACTION`。ChatPost 不截取二维码 token、不记录验证码，也不绕过平台验证。

### 6. 只读确认账号状态

```bash
chatpost account status zhihu@personal --output json
```

至少返回：

```json
{
  "target": "zhihu@personal",
  "runner": "zhihu-personal",
  "state": "READY",
  "checked_at": "<timestamp>"
}
```

公开 display name 可以用于人工确认，但不能作为 Account 主键或写入包含隐私的日志。

### 7. 为固定博客生成 plan

```bash
chatpost plan examples/zhihu/mkdocs-quickstart.md \
  --to zhihu@personal \
  --output json \
  --no-interactive
```

Plan 必须检查：

- 标题存在；
- 正文非空；
- marker 为 `CHATPOST-MKDOCS-SMOKE-V1`；
- 本地图片 `assets/mkdocs-pipeline.png` 可读；
- target、Runner、adapter 和 auth 均 READY；
- ledger 中没有该 source/target 的 active draft；
- 操作是 `create_draft`；
- 本步骤没有远端上传或写入。

### 8. 单次创建草稿

```bash
chatpost draft create examples/zhihu/mkdocs-quickstart.md \
  --to zhihu@personal
```

写入前再次验证同一个 Runner、账号和 source hash。一个 invocation 只允许一个 create RPC，不在异常路径中自动重试。

明确成功时保存：

```text
source_ref
source_sha256
target = zhihu@personal
runner = zhihu-personal
operation = create_draft
draft_id
review_url
status = DRAFT_CREATED
adapter/browser/protocol versions
```

### 9. 回读与人工 Review

```bash
chatpost publication status <publication-ref>
chatpost publication open <publication-ref>
```

回读检查：

| 项目 | 预期 |
|---|---|
| 标题 | `用 MkDocs 搭一个可维护的项目文档站` |
| marker | `CHATPOST-MKDOCS-SMOKE-V1` 唯一存在 |
| 代码 | 至少包含 `mkdocs serve` 与 `mkdocs build --strict` |
| 表格 | 页面职责表存在 |
| 图片 | 本地 PNG 上传并在编辑器可见 |
| 最终发布 | 未点击 |

## 复用已经登录的 Profile

内部验收可以引用此前的隔离 Profile，而不是要求用户重新登录：

```bash
chatpost runner add zhihu-personal \
  --runtime host \
  --profile-mode adopt \
  --user-data-dir <existing-isolated-profile>
```

Adopt 边界：

- 只绑定目录引用，不复制 Profile；
- 不读取 Cookie；
- 不把路径写进公开文档或 ledger；
- 启动前检查目录权限和进程锁；
- 仍然执行 exact extension、bridge 和只读 auth preflight；
- 如果登录已失效，回到可见人工登录 checkpoint。

禁止 adopt 日常 Chrome 默认 Profile。

## 连接面在首次运行中的角色

```text
CDP URL
  ChatPost runner manager -> Chrome
  打开登录页、扩展身份验证、诊断

Bridge WebSocket URL
  browser extension -> bridge server
  扩展主动连接，任务与回执携带 bridge token

Control transport
  ChatPost adapter -> bridge process
  managed local 默认 in-process/stdio；不要求 HTTP URL
```

Managed local Runner 自动分配端口并在证明 exact extension identity 后配置扩展自己的 URL/token 字段。普通用户无需输入 `9227`、`9527` 或 companion port。无法安全配置扩展时进入 `NEEDS_EXTENSION_SETUP`，由用户在扩展设置页完成；不能因此读取知乎 Cookie。

## RESULT_UNKNOWN

如果 create 请求已发出，但 WebSocket 断开、CLI 超时或回执无法验证：

```text
RUNNING -> RESULT_UNKNOWN
```

此时必须：

1. 保留 source hash、target、Runner、开始时间和调用 ID；
2. 释放页面前先保存可用诊断；
3. 禁止再次执行 `draft create`；
4. 通过 `publication status/reconcile` 和人工草稿箱检查恢复；
5. 只有证明第一次没有创建后，才允许用户显式决定下一步。

## 验收矩阵

| 能力 | 离线测试 | 本地 Runner | 真实知乎草稿 |
|---|---:|---:|---:|
| ChatUp descriptor contract | 必需 | 必需 | 间接 |
| Profile lock与端口租约 | 必需 | 必需 | 必需 |
| 二维码扫码登录 | contract | 必需 | 已验证 |
| 短信验证码登录 | contract | 可选 | 待单独验收 |
| exact extension identity | fake + contract | 必需 | 必需 |
| bridge token redaction | 必需 | 必需 | 必需 |
| account auth check | fake | 必需 | 必需 |
| plan 无副作用 | 必需 | 必需 | 不写入 |
| draft create 单次 RPC | fake recorder | 必需 | 恰好一次 |
| receipt/ledger | 必需 | 必需 | 必需 |
| 标题/marker/代码/图片回读 | fixture | 可选 | 必需 |
| 最终 publish 未触发 | contract | contract | 必需 |

## 常见失败

- **Chrome dependency 不存在**：状态为 `CHROME_DEPENDENCY_MISSING`，运行报错中给出的 exact `chatup chrome-for-testing install --version ...`；ChatPost 不回退到未知系统浏览器，也不隐式安装。
- **Profile 被占用**：停止并报告 owner，不强杀日常 Chrome。
- **扩展不匹配**：状态为 `EXTENSION_UNAVAILABLE`，不把任意 service worker 当目标扩展。
- **扩展 URL/token 未配置**：状态为 `NEEDS_EXTENSION_SETUP`，打开 exact extension 设置页，不写入平台 storage。
- **协议兼容性未证明**：状态为 `PROTOCOL_UNVERIFIED`，禁止 auth 之后的真实写入。
- **Bridge 断开**：写操作前失败；写操作后则进入 `RESULT_UNKNOWN`。
- **账号未登录**：打开可见浏览器，等待用户处理。
- **图片不存在**：plan 失败，不创建残缺草稿。
- **ledger 已有 draft ID**：`draft create` 失败，提示显式 `draft update` 或人工处理。
