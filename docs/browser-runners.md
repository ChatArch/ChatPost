# Browser Runner 与账号隔离

!!! warning "状态：架构提案"
    `ChatPost 0.1.0` 已实现 task-specific 知乎 Runner 生命周期，但尚未实现通用 `runner` 或 `account` registry 命令。文中其余多账号/远端模型仍是提案。

总体资源关系见 [总体架构设计](architecture.md)，持久化 schema 见 [配置、环境与状态设计](configuration.md)，具体任务见 [知乎首次设置与草稿验收](zhihu-first-run.md)。

## 直接答案

### Chrome 一定要 Docker 吗？

**不需要。**

Chrome、Chromium 或 Chrome for Testing 都可以作为普通宿主机二进制直接启动：

```text
chrome
  --user-data-dir=<isolated directory>
  --remote-debugging-address=127.0.0.1
  --remote-debugging-port=<unique port>
  --load-extension=<adapter extension>
```

我们已经用这种方式打通 Markdown 到知乎草稿的完整链路，没有使用 Docker。Chrome 官方文档也直接使用 `chrome --headless` 和 `--remote-debugging-port`，因此容器不是浏览器协议的一部分。

ChatPost 首版应默认 `runtime=host`；Docker 作为可选部署后端，在需要镜像复现、进程隔离或服务器调度时使用。

### Chrome 支持多个用户/账号吗？

**Chrome 技术上支持一个 user-data-dir 下包含多个 profile，但 ChatPost 不应把这种子 profile 当作并发账号隔离单位。**

Chromium 官方说明：

- user-data-dir 保存历史、书签、Cookie 和本地状态；
- 每个 Chrome profile 是 user-data-dir 下的子目录；
- 两个运行中的 Chrome 实例不能共享同一个 user-data-dir。

因此 ChatPost 推荐：

```text
一个 browser persona
= 一个 Runner
+ 一个 Chrome 进程
+ 一个独立 user-data-dir
+ 一组独立端口
+ 一个独立 bridge token
```

两个知乎账号应使用两个 persona。不同 persona 可以并行；同一 persona 的发布任务必须串行。

## Browser Persona 是什么

Browser persona 是“这组网页会话属于谁”的运行边界，而不是平台密码容器。

示例：

```text
personal persona
├── zhihu@personal
└── csdn@personal

brand persona
├── zhihu@brand
└── xiaohongshu@brand
```

同一 persona 可以保存不同平台的同一身份组合。如果希望平台之间也完全隔离，可以继续拆成一账号一 persona。

## 为什么不复用 Chrome 的多个子 Profile

在一个 user-data-dir 中使用 `Default`、`Profile 1`、`Profile 2` 对人工浏览很方便，但不适合作为 ChatPost 首版的 Runner 模型：

- user-data-dir 仍由一个 Chrome 实例持有进程锁；
- 多个独立进程无法安全共享它；
- CDP、扩展 service worker 和 bridge 需要额外判断当前属于哪个子 profile；
- 停止、备份、迁移和故障恢复的边界不清晰；
- 账号间仍共享部分 installation-local state。

ChatPost 选择更简单且可审计的边界：每个 Runner 拥有完整独立的 user-data-dir。

## 资源关系

```text
ChatPost control plane
├── source / plan
├── publication ledger
├── account registry
│   ├── zhihu@personal -> mac-personal
│   ├── csdn@personal  -> mac-personal
│   └── zhihu@brand    -> mac-brand
└── runner registry
    ├── mac-personal
    │   ├── host Chrome process
    │   ├── user-data-dir A
    │   ├── CDP port A
    │   └── bridge A
    └── mac-brand
        ├── host Chrome process
        ├── user-data-dir B
        ├── CDP port B
        └── bridge B
```

`account` 是逻辑发布目标；`runner` 是执行环境；`user-data-dir` 是登录态存储位置。三者不能混成一个配置字段。

## 当前 Wechatsync 约束

现有 Wechatsync bridge 内部只有一个 active WebSocket client。新的扩展连接会成为当前 client，因此一个 bridge 不能作为多个账号 Runner 的路由器。

首版 ChatPost 应：

- 每个 Runner 启动一个独立 bridge 实例；
- 为每个 bridge 分配独立端口和 token；
- 先在控制面选择 Runner，再调用该 Runner 的 adapter；
- 不让多个 Chrome Profile 同时连接同一个现有 bridge。

未来可以增加带 `runner_id` 的 broker，但不能在当前协议上假装已经支持多租户。

## 三个连接面

现有实践使用 CDP、extension WebSocket 和 bridge control 三个不同的连接面：

```text
Runner manager -> http://127.0.0.1:<cdp-port> -> Chrome
Browser extension -> ws://127.0.0.1:<bridge-port> -> bridge server
ChatPost adapter -> stdio (或受控 companion HTTP) -> bridge process
```

CDP 用于打开登录页、确认 exact extension identity 和诊断。扩展主动连接 WebSocket server；ChatPost 本地默认通过 in-process/stdio 调用 bridge process。Managed Runner 自动配置这些连接，普通用户无需填写 URL。不能把 CDP、extension WebSocket 或未鉴权 companion HTTP 暴露到公网。

## Host Binary 模式

这是推荐默认值。

### 适合场景

- 本地 Mac/Windows/Linux；
- 首次扫码、短信验证或 CAPTCHA；
- 需要人工打开草稿 Review；
- 单机少量账号；
- Linux 服务器上的 systemd user service。

### 必需资源

```text
ChatUp PlaywrightBrowserInstallation descriptor
extension directory/version
user-data-dir
process identity/PID or service unit
debug address/port
bridge address/port/token reference
control transport/endpoint
runtime logs
```

### ChatUp 管理的 Chrome dependency

已验证实践使用 Playwright 缓存中的 Chrome for Testing 二进制直接运行，没有 Docker。现在由已发布 `chatup 0.2.4` 把这个临时依赖提升为可复用机器环境：

```text
~/.chatarch/playwright/
└── <playwright-version>/{package,browsers,installation.json}
```

用户通过 `chatup playwright install <chatpost-tested-version> --browser chromium` 安装；ChatPost Runner 只通过 `chatup.playwright.resolve(...)` 解析 descriptor，不拥有下载、解压、升级或 browser registry。Chrome 不打进 ChatPost wheel，也不覆盖系统 Chrome；登录态仍只在 Runner 的 `chrome-data/` 中。

### 安全默认值

- user-data-dir 权限仅当前 OS 用户可读写；
- CDP 和 bridge 只监听 `127.0.0.1`；
- 不把 debug port 暴露到局域网或公网；
- 不导出 Cookie；
- 不使用日常 Chrome 的默认 Profile；
- 不让两个 Runner 指向同一个 user-data-dir。

## Docker 模式

Docker 是可选 runtime，而不是要求。

### 适合场景

- 需要固定 Chrome/系统库/扩展版本；
- Linux 服务器统一调度；
- 希望每个 persona 有独立进程和文件系统命名空间；
- 可以承担镜像、显示与持久卷维护。

### 每个容器必须具备

- 固定版本的 Chrome/Chromium；
- 固定版本的扩展；
- 一个持久化 user-data-dir volume；
- 足够的共享内存和正确的 Chrome sandbox 配置；
- 首次登录时的可见浏览器、VNC 或受控人工接管路径；
- 只绑定到宿主机 loopback 的 CDP/bridge 映射。

### 禁止事项

- 不把已登录 profile 烘焙进镜像；
- 不把 profile volume 提交到 Git；
- 不将同一个 volume 挂给多个同时运行的 Chrome；
- 不公开 CDP、VNC 或 bridge 到互联网；
- 不因为运行在容器中就弱化账号/租户权限边界。

## 模式对比

| 维度 | Host binary | Docker |
| --- | --- | --- |
| 首版默认 | 是 | 否 |
| Chrome 安装 | ChatUp-managed Chrome for Testing | 镜像内固定版本（后续 backend） |
| 登录与人工接管 | 最简单 | 需要显示/VNC/受控入口 |
| Profile 持久化 | 普通目录 | 持久卷 |
| 扩展加载 | 本地目录 | 镜像内或只读挂载 |
| 可复现性 | 固定 binary/version | 固定 image digest |
| 隔离级别 | OS 进程 + 目录权限 | 容器 + volume；强租户仍建议 OS user/VM |
| 运维复杂度 | 较低 | 较高 |

## 多账号配置示例

以下只是预期的通用多账号 TOML schema，不是 `0.1.0` task-specific Runner 已支持配置：

```toml
[runners.mac-personal]
runtime = "host"
profile_mode = "managed"

[runners.mac-personal.bridge]
ws_bind = "127.0.0.1"
ws_port = "auto"
control_transport = "stdio"
token_profile = "personal"

[runners.mac-brand]
runtime = "host"
profile_mode = "managed"

[runners.mac-brand.bridge]
ws_bind = "127.0.0.1"
ws_port = "auto"
control_transport = "stdio"
token_profile = "brand"

[accounts."zhihu@personal"]
platform = "zhihu"
runner = "mac-personal"

[accounts."csdn@personal"]
platform = "csdn"
runner = "mac-personal"

[accounts."zhihu@brand"]
platform = "zhihu"
runner = "mac-brand"
```

`token_profile` 指向 ChatEnv profile，配置文件本身不保存 token 明文。完整 schema 和旧 Wechatsync 变量迁移见 [配置、环境与状态设计](configuration.md)。

## 端口与锁

每个 Runner 需要独立租约：

```text
user_data_dir lock
CDP port lease
bridge WebSocket port lease
optional companion control port lease
job lock
```

建议由 ChatPost 自动分配并持久化端口，不要求用户记忆固定数字。

启动前检查：

1. user-data-dir 没有被其他 Runner 占用；
2. CDP/bridge 端口未被占用；
3. ChatUp descriptor 可只读解析到 exact、可执行的 Chrome binary，且扩展版本存在；
4. 目录权限符合要求；
5. bridge 只绑定 loopback；
6. Runner identity 与已有进程匹配。

## 并发模型

```text
同一个 persona
  -> 同时只允许一个写任务
  -> auth/status 等只读命令也要避免干扰正在写入的页面

不同 persona
  -> 可以并行
  -> 前提是 user-data-dir、端口和 bridge 均独立
```

创建/更新请求进入平台后如果连接中断，不释放锁并自动重试，而是记录 `RESULT_UNKNOWN`，等待回查。

## 登录与恢复

`account login` 是人工 checkpoint：

1. 启动或打开正确 Runner；
2. 导航到平台登录页；
3. 用户扫码、输入验证码或完成平台要求；
4. ChatPost 不读取密码或验证码；
5. adapter 运行只读 auth check；
6. ledger 只记录最近验证时间和状态，不记录 Cookie。

如果平台主动注销、Profile 损坏或 Chrome 版本不兼容，状态进入 `NEEDS_LOGIN` 或 `NEEDS_ACTION`，而不是自动复制其他账号的 session。

## 多人和强租户隔离

独立 user-data-dir 足以隔离同一个人管理的多个普通账号，但不是完整的恶意多租户安全边界。

建议层级：

| 场景 | 最低隔离 |
| --- | --- |
| 同一用户的多个平台账号 | 独立 persona/user-data-dir |
| 同一用户的多个高价值品牌账号 | 独立 persona，最好独立 OS service account 或 container |
| 不同人/团队/租户 | 独立 OS user、container 或 VM，并独立 secret store |
| 不可信远端执行节点 | 不直接授予 profile；使用受控 runner 注册和最小权限 |

## 数据边界

ChatPost 可以保存：

- Runner 名称、runtime、版本和健康状态；
- user-data-dir 的路径引用；
- account 到 Runner 的逻辑映射；
- draft/article ID、内容 hash、receipt 和状态；
- secret reference 名称。

ChatPost 不保存：

- Chrome Profile 文件内容；
- Cookie、Local Storage 或请求头；
- 平台密码、短信验证码；
- bridge token 明文；
- 私密 profile 的压缩备份。

## 首版决策摘要

```text
默认 runtime       = host binary
Chrome owner        = ChatUp (`~/.chatarch/playwright/`)
ChatPost resolution = read-only `chatup.playwright.resolve`
Docker             = optional
隔离单位           = browser persona / runner
同平台多个账号     = 多个独立 user-data-dir
同 profile 并发写入 = 禁止
不同 profile 并发   = 允许
bridge              = 每 runner 一个实例
本地 control        = in-process / stdio 优先
网络绑定           = loopback only
最终发布           = 人工 Review checkpoint
```

## 参考资料

- Chromium User Data Directory: <https://chromium.googlesource.com/chromium/src/+/HEAD/docs/user_data_dir.md>
- Chrome Headless: <https://developer.chrome.com/docs/chromium/headless>
- ChatUp Chrome CLI: <https://arch.gh.wzhecnu.cn/ChatUp/cli-tree/>
- Wechatsync bridge server: <https://github.com/ChatArch/Wechatsync/blob/dev/packages/mcp-server/src/ws-bridge.ts>
- Wechatsync extension WebSocket client: <https://github.com/ChatArch/Wechatsync/blob/dev/packages/extension/src/mcp/client.ts>
