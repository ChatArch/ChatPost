# ChatPost 文档

ChatPost 是 ChatArch 的多平台内容发布控制面。这个文档站把已验证的知乎浏览器链路、首个功能版本设计和当前真实实现状态分开呈现。

站点入口：<https://arch.gh.wzhecnu.cn/ChatPost/>

## 按场景选择文档

| 场景 | 文档 |
| --- | --- |
| 先理解 control plane、Browser Runner、Account 和 Publication | [总体架构](architecture.md) |
| Review Chrome 安装、ChatEnv、URL、Profile 和 ledger | [配置、环境与状态](configuration.md) |
| 用固定 MkDocs 博客稿理解知乎首次登录与草稿验收 | [知乎首次设置与草稿验收](zhihu-first-run.md) |
| 第一次安装、运行命令行、确认包可用 | [CLI 树](cli-tree.md) |
| Review 预期 CLI、Chrome runtime 与多账号隔离 | [Browser Runner 与账号隔离](browser-runners.md) |
| 校对当前包有哪些一等能力和边界 | [能力地图](capability-map.md) |
| 从 Python 代码调用包能力 | [Python 接口树](interface-tree.md) |

## 文档栏目组织

当前站点只保留长期有用的文档入口，不生成空泛路线图：

- **总体架构**：控制面、执行面和核心资源的责任边界。
- **配置、环境与状态**：Chrome 安装、ChatEnv secrets、Runner state 和 publication ledger。
- **知乎首次设置与草稿验收**：用固定博客稿定义可验证的首次登录和单次 draft create。
- **CLI 树**：最直观的命令展示入口，包含真实命令树、状态和更新清单。
- **Browser Runner 与账号隔离**：解释 host binary、Docker、多账号 user-data-dir 和 bridge 边界。
- **能力地图**：当前一等能力、边界和不负责的范围。
- **接口树**：命令行背后的可 import Python 接口。

## 核心入口

<div class="grid cards" markdown>

- **总体架构**

    先看 Browser、Runner、Account、Publication 如何组成控制面与执行面。

    [查看总体架构](architecture.md)

- **配置、环境与状态**

    Review ChatArch 内部 Chrome 二进制、三个连接面、ChatEnv secret 和目录布局。

    [查看配置设计](configuration.md)

- **知乎首次设置与草稿验收**

    从固定 MkDocs 博客稿出发，查看首次登录、plan、单次 draft create 和回读契约。

    [查看知乎任务流](zhihu-first-run.md)

- **CLI 树**

    从命令行入口开始，记录已实现命令、命令状态和交互约定。

    [查看 CLI 树](cli-tree.md)

- **能力地图**

    用于 review 当前包的能力边界，避免把规划写成已实现功能。

    [查看能力地图](capability-map.md)

- **Browser Runner 与账号隔离**

    Review Chrome 是否依赖 Docker、多个账号如何隔离，以及 Runner/Account 的资源关系。

    [查看 Browser Runner 设计](browser-runners.md)

- **Python 接口树**

    保持命令行是薄入口，实质能力放在可 import 的 Python 接口中。

    [查看接口树](interface-tree.md)

</div>

## 文档状态约定

- **已实现**：代码、测试或 CLI 路径已经存在。
- **已验证**：已经通过本地 smoke、CI 或真实服务实践验证。
- **未实现**：只写边界和计划，不写成可执行教程；实现并验证后再升级为操作文档。

## 本地预览

```bash
python -m pip install -e ".[docs]"
mkdocs serve
```

英文首页见站点语言入口：<https://arch.gh.wzhecnu.cn/ChatPost/en/>。缺少英文翻译的专题页会按 i18n fallback 回退到中文页面。
