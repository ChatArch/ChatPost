# Python 接口树

命令行只做参数解析；实质能力位于 `chatpost.accounts` 和 `chatpost.zhihu`。

```text
chatpost.accounts
├── Account
├── AccountRegistryError
├── default_chatpost_home()       # 默认 ~/.chatarch/chatpost，可由 CHATPOST_HOME 覆盖
├── default_registry_path()       # 默认 ~/.chatarch/chatpost/accounts.toml，可由 CHATPOST_ACCOUNT_REGISTRY 覆盖
├── load_accounts(path=None)
└── resolve_account(target, accounts)

chatpost.zhihu
├── ZhihuBrowserConfig            # 纯浏览器登录配置
├── load_browser_config(path)     # 不读取 adapter/env/extension 字段
├── browser_preflight(config)
├── browser_status(config)
├── browser_login(config, timeout=..., event_callback=...)
├── browser_logout(config)
├── browser_login_session(config)
├── ZhihuRunnerConfig             # 后续发布 adapter/Wechatsync runner 配置边界
└── load_runner_config(path)      # 发布 runner 专用；不得被 login/status/logout 默认调用
```

## ChatUp / ChatBrowser dependency

```python
from chatup.playwright import resolve
import chatbrowser
```

ChatPost 只解析已存在的 exact Playwright browser installation，不隐式安装或升级。ChatBrowser 负责浏览器 runtime、Profile metadata 和 CDP session metadata 的安全边界；ChatPost 不保存 Cookie、LocalStorage、IndexedDB、session、token 或 QR payload。

## 示例：默认 ChatArch state root 读取 Profile registry

```python
from chatpost.accounts import default_registry_path, load_accounts, resolve_account
from chatpost.zhihu import browser_status, load_browser_config

registry_path = default_registry_path()  # ~/.chatarch/chatpost/accounts.toml
accounts = load_accounts(registry_path)
account = resolve_account("zhihu@zhihu-personal", accounts)
config = load_browser_config(account.runner_config)
status = browser_status(config)
```

默认状态根目录是 `~/.chatarch/chatpost/`。任务实验可以显式传 `load_accounts(path)` 或 CLI `--registry PATH`，但普通用户默认不需要在仓库根目录或当前目录放 `accounts.toml`。

## Wechatsync 接入边界

`ZhihuRunnerConfig` / `load_runner_config()` 保留给后续发布 adapter 接入。它可以包含 extension、bridge、env 和 adapter CLI 字段；但 `browser_status()`、`browser_login()` 和 `browser_logout()` 必须继续使用 `ZhihuBrowserConfig`，不能为了发布接入重新依赖 Wechatsync、发布 token、Cookie、LocalStorage 或 IndexedDB。