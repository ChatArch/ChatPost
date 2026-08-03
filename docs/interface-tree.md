# Python 接口树

`ChatPost` 的 CLI 应保持薄入口；实质能力应放在可 import 的 Python 函数、类或 service 层里。

## 包入口

```python
from chatpost import __version__
```

## 待补接口

```text
chatpost
├── cli.py           # Click 入口，只做参数解析和输出
├── dependencies.py  # 只读解析 ChatUp Chrome descriptor；不安装
├── runner.py        # Profile/process/CDP/bridge 生命周期
├── account.py       # platform@alias 与登录 checkpoint
└── publication.py   # plan/draft/ledger/reconcile
```

Chrome 环境 contract 直接消费 ChatUp 已发布 public API：

```python
from chatup.chrome_for_testing import ChromeForTestingInstallation, resolve
```

ChatPost dependency adapter 只能封装只读 `resolve(...)` 和领域错误；不能复制 downloader/extractor，也不能在 `runner start` 中调用 `install(...)` 隐式安装。

## 更新清单

- 每个实质 CLI 命令都要能映射到 importable API。
- 文档里的函数签名应和代码一致。
- 对外输出默认不要泄漏 token、cookie、内部 URL 或人员信息。
