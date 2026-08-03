# 能力地图

这个页面用于校对 `ChatPost` 当前有哪些一等能力、哪些能力已经验证，以及哪些事情不属于当前包。

## 能力分组

<div class="grid cards" markdown>

- **命令行入口**

    `chatpost --help` 和 `chatpost --version` 是默认可验证入口。

- **Python 接口**

    实质能力应放到可 import 的 Python 函数、类或 service 层，而不是只写在 Click 回调里。

- **配置与环境**

    已有 ChatEnv provider 脚手架；生产 schema 提案把非秘密 TOML、ChatEnv secret profile、runtime state 和 ledger 分开。

- **Browser Runner 设计**

    已形成 ChatArch-managed Chrome、host binary、Docker、多账号 user-data-dir 与 bridge 隔离提案；尚未实现 Browser/Runner 命令。

- **任务导向的知乎验收**

    仓库已加入固定 MkDocs 博客稿与本地图片；后续只用一次明确 draft create 验证 ChatPost，不自动最终发布。

</div>

## 当前边界

| 能力 | 状态 | 说明 |
| --- | --- | --- |
| 命令行基础入口 | 已实现 | 模板生成 Click group、`--version` 和基础测试。 |
| ChatEnv 配置提供者 | 脚手架已实现 | `config.py` 与 `chatenv.configs` 存在，但当前 `CHATPOST_API_KEY` 只是占位，生产 bridge schema 尚未实现。 |
| 总体架构与配置模型 | 提案 | 已定义 Browser/Runner/Account/Publication、ChatArch Home、ChatEnv 和 ledger 边界。 |
| CLI 结构设计 | 提案 | 已定义 browser/runner/account/plan/draft/publication 边界，但命令尚不存在。 |
| Browser 安装与 Runner 隔离 | 提案 | 默认 ChatArch-managed Chrome for Testing、host binary、每 Runner 独立 user-data-dir/bridge；尚未实现。 |
| 历史知乎草稿链路 | 已验证 | Wechatsync 实践已用直接二进制、独立 Profile 和 loopback bridge 创建并回读草稿。 |
| MkDocs 知乎测试稿 | 已加入 | `examples/zhihu/mkdocs-quickstart.md` 与本地 PNG 已存在；尚未通过 ChatPost 命令创建草稿。 |
| 业务命令 | 未实现 | 按当前包真实需求补充，不能在模板里伪造未来命令。 |

## 不在当前范围

- 不生成计划类占位页。
- 不把未实现能力写成用户可执行教程。
- 设计文档中的命令必须持续标注为“提案”，直到代码、测试和 help text 都存在。
- 固定博客稿存在不代表 ChatPost 端到端链路已经实现或已经创建新草稿。
- 不在 README、docs、issue、PR 评论或 CI log 中输出 secret、token、cookie 或 Authorization header。
