# 能力地图

本页区分 `ChatPost 0.1.0` 的真实能力、已验证的外部链路，以及仍属提案的资源模型。

## 已实现

| 能力 | 状态 | 说明 |
|---|---|---|
| CLI 基础入口 | 已实现 | `chatpost --help`、`--version`。 |
| 知乎静态检查 | 已实现 | `chatpost zhihu preflight` 检查 exact Playwright install、Profile/secret 权限、Node、扩展、CLI 和数值 IPv4 loopback `127.0.0.1` 端口；拒绝 `localhost` 与 IPv6 loopback。 |
| 首次登录 checkpoint | 已实现 | `chatpost zhihu login` 保持同一 Profile 并循环只读 auth，供人工扫码/验证码；不写文章。 |
| 知乎登录检查 | 已实现 | `chatpost zhihu auth` 启动受控 Runner，调用 Wechatsync 只读 auth，然后优雅停止。 |
| 文章 dry-run | 已实现 | `chatpost zhihu draft dry-run` 不启动浏览器、不写知乎。 |
| 单次草稿创建 | 已实现 | `chatpost zhihu draft create` 只调用一次 adapter；browser/adapter 启动前捕获 source digest，成功写 `0600` receipt，唤醒后任何输出/读取状态不明均写 `RESULT_UNKNOWN`。本轮 popup、browser 与 adapter cleanup 分别记录；写入后 source 或 receipt I/O 失败仍保留 authoritative result，不能据此重试。 |
| ChatUp Playwright dependency | 已实现 | 有界依赖 `chatup>=0.2.4,<0.3.0`，只读调用 `chatup.playwright.resolve`。 |
| 原始 CDP 扩展唤醒 | 已实现 | 通过启动时捕获的 browser WebSocket 和本轮 `Target.createTarget` 返回的 exact popup ID；`Target.attachToTarget` 前按 exact ID/URL/type 重验，忽略 stale restored popup 与 service worker，也不跟随 target-level WebSocket。cleanup 只用 `Target.closeTarget` 关闭本轮 popup；bridge listener PID 必须属于本轮 Node 子进程。 |
| Secret redaction | 已实现 | adapter 输出遮蔽 env 精确值及动态私密赋值（包括跨行结构化私密赋值）、WebSocket/loopback 连接和 ownership marker，同时保留知乎 review URL；启动诊断在私有 env 不可用时整段 fail-closed；receipt 不保存 token、Cookie 或 LocalStorage。 |

## 已验证事实

- 历史 Baseline 在本地 Mac 使用 Playwright cache 的 CFT 149、持久 Profile、Wechatsync 扩展和 loopback bridge 创建并回读知乎草稿。
- ChatUp `1.61.1/chromium` task-local 真实安装解析到 revision `1228`、CFT `149.0.7827.55`，doctor 为 `READY`。
- ChatPost 单元测试锁定 loopback、exact resolver、单次 create、歧义不重试和 receipt 边界。
- 第二篇 Infra 草稿是否通过新命令创建，以任务报告和真实编辑链接回读为准；不能仅凭单元测试宣称完成。

## 责任边界

| Owner | 负责 | 不负责 |
|---|---|---|
| ChatUp | Playwright package/browser 安装、版本、revision、路径、doctor | Profile、登录、扩展、草稿 |
| ChatPost | Profile、浏览器生命周期、CDP、bridge、任务门、receipt | 下载 browser、知乎最终发布 |
| Wechatsync | 知乎 adapter、内容转换和草稿写入 | 机器 browser 安装、长期 ledger |
| 人工 | 首次登录、编辑页 Review、最终发布 | 自动化 secret 导出 |

## 仍属提案

- 通用 `runner` / `account` / `publication` 命令；
- 多账号调度与长期 publication ledger；
- same-ID 文章更新；
- 自动最终发布；
- Playwright Page/Locator 自动化。

这些能力不能进入当前 Quick Start，直到代码、测试和真实验收都存在。
