# 能力地图

这个页面用于校对 `ChatPost` 当前有哪些一等能力、哪些能力已经验证，以及哪些事情不属于当前包。

## 能力分组

<div class="grid cards" markdown>

- **命令行入口**

    `chatpost --help` 和 `chatpost --version` 是默认可验证入口。

- **Python 接口**

    实质能力应放到可 import 的 Python 函数、类或 service 层，而不是只写在 Click 回调里。

- **配置与环境**

    默认接入 ChatEnv；长期、常用、跨命令共享的配置放入 `config.py`。

- **Browser Runner 设计**

    已形成 host binary、Docker、多账号 user-data-dir 与 bridge 隔离提案；尚未实现 Runner 命令。

</div>

## 当前边界

| 能力 | 状态 | 说明 |
| --- | --- | --- |
| 命令行基础入口 | 已实现 | 模板生成 Click group、`--version` 和基础测试。 |
| ChatEnv 配置提供者 | 已实现 | 默认生成 `config.py` 和 `chatenv.configs` 入口点。 |
| CLI 结构设计 | 提案 | 已定义 runner/account/plan/draft/publication 边界，但命令尚不存在。 |
| Browser Runner 与多账号隔离 | 提案 | 默认 host binary、每 Runner 独立 user-data-dir/bridge；尚未实现。 |
| 业务命令 | 未实现 | 按当前包真实需求补充，不能在模板里伪造未来命令。 |

## 不在当前范围

- 不生成计划类占位页。
- 不把未实现能力写成用户可执行教程。
- 设计文档中的命令必须持续标注为“提案”，直到代码、测试和 help text 都存在。
- 不在 README、docs、issue、PR 评论或 CI log 中输出 secret、token、cookie 或 Authorization header。
