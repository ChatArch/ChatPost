# 能力地图

本页区分 `ChatPost 0.1.x` 的真实能力、已验证的外部链路，以及仍属提案的资源模型。

## 已实现

| 能力 | 状态 | 说明 |
|---|---|---|
| CLI 基础入口 | 已实现 | `chatpost --help`、`--version`。 |
| 通用账号查看 | 已实现 | `chatpost account list/show` 读取只含非敏感 metadata 的账号 alias registry；输出 alias、platform、runner_config、profile、label，不保存或回显 Cookie、LocalStorage、token、password 或 credential。 |
| 通用登录 checkpoint | 已实现 | `chatpost login status/qr/qr-image/qr-link/code` 解析 `platform@alias` 并复用平台 runner 做只读 auth、live QR 图片 artifact handoff、公开登录 URL 的 QR/link handoff 或验证码 checkpoint；登录态仍保留在浏览器 Profile 中，手机号、验证码、QR payload、Cookie 和 LocalStorage 不进入 CLI 参数、registry、config、receipt 或日志。 |
| 通用 QR artifact 生成 | 已实现 | `chatpost qr encode` 把调用方提供的数据渲染为 PNG artifact，默认只报告 artifact metadata；平台发送仍由宿主/gateway 负责。 |
| 通用发 Post 草稿 | 已实现 | `chatpost post draft` 解析 `platform@alias` 与 source，调用平台 create 路径一次，写 `0600` receipt；这是当前“发 Post”的 review 草稿入口，不是最终发布。 |
| 知乎静态检查 | 已实现 | `chatpost zhihu preflight` 检查 exact Playwright install、Profile/secret 权限、Node、扩展、CLI 和数值 IPv4 loopback `127.0.0.1` 端口；拒绝 `localhost` 与 IPv6 loopback。 |
| 首次登录 checkpoint | 已实现 | `chatpost zhihu login` 保持同一 Profile 并循环只读 auth，供人工扫码/验证码；通用 `chatpost login code` 已提供验证码 checkpoint 入口，但端到端新号短信验收仍需人工手机号/验证码后执行；不写文章。 |
| 知乎登录检查 | 已实现 | `chatpost zhihu auth` 启动受控 Runner，调用 Wechatsync 只读 auth，然后优雅停止。 |
| 文章 dry-run | 已实现 | `chatpost zhihu draft dry-run` 不启动浏览器、不写知乎。 |
| 单次草稿创建 | 已实现 | `chatpost zhihu draft create` 只调用一次 adapter；browser/adapter 启动前捕获 source digest，成功写 `0600` receipt，唤醒后任何输出/读取状态不明均写 `RESULT_UNKNOWN`。本轮 popup、browser 与 adapter cleanup 分别记录；写入后 source 或 receipt I/O 失败仍保留 authoritative result，不能据此重试。 |
| Existing-CDP attach 模式 | 已实现 | `attach_existing_cdp = true` 允许已知 loopback CDP browser 继续持有 Profile；ChatPost 只创建本轮 extension popup、启动 MCP watch、执行 adapter 任务、关闭本轮 popup，并保留现有 browser 运行。 |
| ChatUp / ChatBrowser / QR dependency | 已实现 | 有界依赖 `chatup>=0.2.4,<0.3.0`、`chatbrowser>=0.1.2,<0.2.0` 和 `qrcode[pil]>=7.4,<9.0`；ChatUp 提供 browser 安装/解析，ChatBrowser 提供 runtime/Profile/CDP metadata 安全边界，qrcode 渲染 QR 图片 artifact 且不耦合平台上传。 |
| 原始 CDP 扩展唤醒 | 已实现 | 通过启动时捕获的 browser WebSocket 和本轮 `Target.createTarget` 返回的 exact popup ID；`Target.attachToTarget` 前按 exact ID/URL/type 重验，忽略 stale restored popup 与 service worker，也不跟随 target-level WebSocket。cleanup 只用 `Target.closeTarget` 关闭本轮 popup；bridge listener PID 必须属于本轮 Node 子进程。 |
| Secret redaction | 已实现 | adapter 输出遮蔽 env 精确值及动态私密赋值（包括跨行结构化私密赋值中的嵌套 object/array 与跨行 quoted value）；无法证明闭合边界时丢弃未知尾部，仅恢复严格知乎 `/edit` review URL 白名单。WebSocket/loopback 连接和 ownership marker 同样遮蔽；启动诊断在私有 env 不可用时整段 fail-closed；receipt 不保存 token、Cookie 或 LocalStorage。 |

## 已验证事实

- 历史 Baseline 在本地 Mac 使用 Playwright cache 的 CFT 149、持久 Profile、Wechatsync 扩展和 loopback bridge 创建并回读知乎草稿。
- ChatUp `1.61.1/chromium` task-local 真实安装解析到 revision `1228`、CFT `149.0.7827.55`，doctor 为 `READY`。
- ChatPost 单元测试锁定通用 `account/login/post` CLI、loopback、exact resolver、单次 create、歧义不重试和 receipt 边界。
- 当前真实草稿链路是否完成，以任务报告和真实编辑链接回读为准；不能仅凭单元测试宣称端到端完成。

## 责任边界

| Owner | 负责 | 不负责 |
|---|---|---|
| ChatUp | Playwright package/browser 安装、版本、revision、路径、doctor | Profile、登录、扩展、草稿 |
| ChatBrowser | 浏览器 runtime、Profile metadata、CDP session metadata | 平台 adapter、内容发布、Cookie 导出 |
| ChatPost | 账号 alias、QR 图片 artifact、Profile、浏览器生命周期、CDP、bridge、任务门、receipt | 下载 browser、知乎最终发布、平台 media 上传 |
| Wechatsync | 知乎 adapter、内容转换和草稿写入 | 机器 browser 安装、长期 ledger |
| 人工 | 首次登录、编辑页 Review、最终发布 | 自动化 secret 导出 |

## 仍属提案

- 通用 `runner` 管理命令；
- 长期 `publication list/show/retry` ledger 命令；
- 多账号调度策略；
- same-ID 文章更新；
- 自动最终发布；
- Playwright Page/Locator 自动化。

这些能力不能进入当前 Quick Start，直到代码、测试和真实验收都存在。
