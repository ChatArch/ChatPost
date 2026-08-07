# 能力地图

本页区分 `ChatPost 0.1.x` 的真实能力、已验证的外部链路，以及仍属提案的资源模型。

## 已实现

| 能力 | 状态 | 说明 |
|---|---|---|
| CLI 基础入口 | 已实现 | `chatpost --help`、`--version`、`--tree`；`--tree` 打印真实注册 CLI 树、叶子接口形状和用途说明。 |
| 平台与 Profile 发现 | 已实现 | `chatpost platforms`、`chatpost profiles --platform zhihu` 和 `chatpost zhihu profiles` 列出可用平台与非敏感 Chrome/Profile target metadata；输出 alias、platform、runner_config、profile、label，不保存或回显 Cookie、LocalStorage、token、password 或 credential。 |
| 知乎登录/状态/登出 | 已实现 | `chatpost zhihu login/status/logout PROFILE` 解析 Profile alias 并复用知乎 runner；`login` 是单条二维码 handoff 命令：打开当前 Profile 的知乎登录页、等待二维码可扫、用同一登录页正在轮询的 page-owned `login_url` 生成 QR 图片/写 `0600` receipt，并继续等 `READY`；`status` 只读 auth；`logout` 只清理知乎 origin 登录态，不读取 session 值。手机号、验证码、Cookie 和 LocalStorage 不进入 CLI 参数、registry、config、receipt 或日志。 |
| Hidden compatibility | 已实现 | 旧脚本入口 `chatpost account list/show`、`chatpost qr encode`、`chatpost zhihu account status/preflight/login qr/login qr-artifact/login code` 保持可调用但不进 `--help`/`--tree`；平台发送仍由宿主/gateway 负责，ChatPost CLI 不输出 `MEDIA:ssh://...` 或 `[media attachment]`。 |
| 知乎草稿 | 已实现 | `chatpost zhihu draft dry-run/create PROFILE SOURCE` 解析 Profile alias 与 source；`dry-run` 不启动浏览器、不写知乎，`create` 只调用一次 adapter，browser/adapter 启动前捕获 source digest，成功写 `0600` receipt，唤醒后任何输出/读取状态不明均写 `RESULT_UNKNOWN`。本轮 popup、browser 与 adapter cleanup 分别记录；写入后 source 或 receipt I/O 失败仍保留 authoritative result，不能据此重试；这是 review 草稿入口，不是最终发布。 |
| Existing-CDP attach 模式 | 已实现 | `attach_existing_cdp = true` 允许已知 loopback CDP browser 继续持有 Profile；ChatPost 只创建本轮 extension popup、启动 MCP watch、执行 adapter 任务、关闭本轮 popup，并保留现有 browser 运行。 |
| ChatUp / ChatBrowser / QR dependency | 已实现 | 有界依赖 `chatup>=0.2.4,<0.3.0`、`chatbrowser>=0.1.2,<0.2.0` 和 `qrcode[pil]>=7.4,<9.0`；ChatUp 提供 browser 安装/解析，ChatBrowser 提供 runtime/Profile/CDP metadata 安全边界，qrcode 渲染 QR 图片 artifact 且不耦合平台上传。 |
| 原始 CDP 扩展唤醒 | 已实现 | 通过启动时捕获的 browser WebSocket 和本轮 `Target.createTarget` 返回的 exact popup ID；`Target.attachToTarget` 前按 exact ID/URL/type 重验，忽略 stale restored popup 与 service worker，也不跟随 target-level WebSocket。cleanup 只用 `Target.closeTarget` 关闭本轮 popup；bridge listener PID 必须属于本轮 Node 子进程。 |
| Secret redaction | 已实现 | adapter 输出遮蔽 env 精确值及动态私密赋值（包括跨行结构化私密赋值中的嵌套 object/array 与跨行 quoted value）；无法证明闭合边界时丢弃未知尾部，仅恢复严格知乎 `/edit` review URL 白名单。WebSocket/loopback 连接和 ownership marker 同样遮蔽；启动诊断在私有 env 不可用时整段 fail-closed；receipt 不保存 token、Cookie 或 LocalStorage。 |

## 已验证事实

- 历史 Baseline 在本地 Mac 使用 Playwright cache 的 CFT 149、持久 Profile、Wechatsync 扩展和 loopback bridge 创建并回读知乎草稿。
- ChatUp `1.61.1/chromium` task-local 真实安装解析到 revision `1228`、CFT `149.0.7827.55`，doctor 为 `READY`。
- ChatPost 单元测试锁定 Profile-based `platforms/profiles/zhihu login/logout/status/draft` CLI、hidden compatibility、`--tree`、live QR `login_url` 提取、loopback、exact resolver、单次 create、歧义不重试和 receipt 边界。
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
