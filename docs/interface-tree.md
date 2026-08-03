# Python 接口树

命令行只做参数解析；实质能力位于 `chatpost.zhihu`。

```text
chatpost.zhihu
├── ZhihuRunnerConfig
├── load_runner_config(path)
├── preflight(config)
├── browser_session(config)
├── execute_task(config, source, mode=...)
├── ResultUnknownError
└── RESULT_UNKNOWN
```

## ChatUp dependency

```python
from chatup.playwright import PlaywrightBrowserInstallation, resolve
```

ChatPost 只解析已存在的 exact Playwright browser installation，不隐式安装或升级。

## 示例

```python
from chatpost.zhihu import execute_task, load_runner_config, preflight

config = load_runner_config("runner.toml")
status = preflight(config)
result = execute_task(config, "article.md", mode="dry-run")
```

`execute_task(..., mode="create")` 是外部写操作：调用方必须保留 receipt，并在 `ResultUnknownError` 后停止自动重试、先去知乎草稿箱消歧。

`browser_session()` 直接启动 ChatUp resolver 返回的浏览器二进制，使用持久 Profile、unpacked extension 和 loopback CDP；它不提供 Playwright Page/Locator API。
