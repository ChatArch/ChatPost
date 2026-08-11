# ChatPost 文档

ChatPost 当前用户可见重点是 **纯浏览器登录基础层 + 独立知乎 draft 入口**：发现平台、发现 Profile、检查知乎/小红书网页登录态、登录 handoff、登出/清理，通过 Wechatsync 创建知乎草稿，并为小红书提供二维码图片登录 handoff。

| 场景 | 文档 |
| --- | --- |
| 立即跑知乎登录与草稿路径 | [Quickstart：逻辑 Profile、知乎登录与草稿](quickstart.md) |
| 查看真实 CLI 树 | [CLI 树](cli-tree.md) |
| 校对当前包有哪些一等能力和边界 | [能力地图](capability-map.md) |
| 理解总体资源和数据流 | [总体架构](architecture.md) |
| Review Chrome 安装、Profile 与状态边界 | [配置、环境与状态](configuration.md) |
| 从 Python 代码调用包能力 | [Python 接口树](interface-tree.md) |

## 当前稳定入口

```bash
chatpost --tree
chatpost platforms
chatpost profiles --platform zhihu
chatpost profiles --platform xhs
chatpost zhihu profiles
chatpost zhihu status PROFILE
chatpost zhihu login PROFILE
chatpost zhihu logout PROFILE
chatpost zhihu draft PROFILE SOURCE --dry-run
chatpost zhihu draft PROFILE SOURCE --receipt PATH
chatpost xhs profiles
chatpost xhs status PROFILE
chatpost xhs login PROFILE --qrcode PATH
chatpost xhs logout PROFILE
```

默认 registry 是 `~/.chatarch/chatpost/accounts.toml`（可用 `CHATPOST_ACCOUNT_REGISTRY` 或 `--registry PATH` 显式覆盖）。`login/status/logout` 只做 browser-level 事情：不调用发布适配器，不加载发布扩展，不要求发布 token，不读取或导出 Cookie/LocalStorage/IndexedDB/session/token。`chatpost zhihu draft` 是独立 Wechatsync adapter 入口：dry-run 用 CLI parser 预览，create 用 extension MCP direct bridge 创建一个草稿，不最终发布。小红书当前只提供 `profiles/login/status/logout`；`login` 写二维码 artifact 并只输出 `qrcode_path`，不把短期确认链接或二维码 token 暴露为用户接口。
