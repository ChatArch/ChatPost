# Python 接口树

命令行只做参数解析；实质能力位于 `chatpost.accounts` 和 `chatpost.zhihu`。

```text
chatpost.accounts
├── Account
├── AccountRegistryError
├── default_registry_path()
├── load_accounts(path=None)
└── resolve_account(target, accounts)

chatpost.zhihu
├── ZhihuRunnerConfig
├── load_runner_config(path)
├── preflight(config)
├── browser_session(config)
├── wait_for_login(config, timeout=...)
├── execute_task(config, source, mode=...)
├── ResultUnknownError
└── RESULT_UNKNOWN
```

## ChatUp / ChatBrowser dependency

```python
from chatup.playwright import PlaywrightBrowserInstallation, resolve
import chatbrowser
```

ChatPost 只解析已存在的 exact Playwright browser installation，不隐式安装或升级。ChatBrowser 负责浏览器 runtime、Profile metadata 和 CDP session metadata 的安全边界；ChatPost 不保存 Cookie、LocalStorage 或 QR payload。

## 示例

```python
from chatpost.accounts import load_accounts, resolve_account
from chatpost.zhihu import execute_task, load_runner_config, preflight

accounts = load_accounts("accounts.toml")
account = resolve_account("zhihu@zhihu-test", accounts)
config = load_runner_config(account.runner_config)
status = preflight(config)
result = execute_task(config, "article.md", mode="dry-run")
```

`execute_task(..., mode="create")` 是外部写操作：调用方必须保留 receipt，并在 `ResultUnknownError` 后停止自动重试、先去知乎草稿箱消歧。

`browser_session()` 直接启动 ChatUp resolver 返回的浏览器二进制，使用持久 Profile、unpacked extension 和 loopback CDP；它不提供 Playwright Page/Locator API。
