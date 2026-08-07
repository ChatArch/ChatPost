# Python Interface Tree

The CLI only parses arguments. Substantive behavior lives in `chatpost.accounts` and `chatpost.zhihu`.

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

## ChatUp / ChatBrowser Dependency

```python
from chatup.playwright import PlaywrightBrowserInstallation, resolve
import chatbrowser
```

ChatPost resolves an existing exact Playwright browser installation. It never installs or upgrades one implicitly. ChatBrowser owns the browser runtime, Profile metadata, and CDP session metadata safety boundary; ChatPost does not store cookies, local storage, or QR payloads.

## Example

```python
from chatpost.accounts import load_accounts, resolve_account
from chatpost.zhihu import execute_task, load_runner_config, preflight

accounts = load_accounts("accounts.toml")
account = resolve_account("zhihu@zhihu-test", accounts)
config = load_runner_config(account.runner_config)
status = preflight(config)
result = execute_task(config, "article.md", mode="dry-run")
```

`execute_task(..., mode="create")` is an external write. Callers must retain its receipt and stop automatic retries after `ResultUnknownError` until the Zhihu draft box is reconciled.

`browser_session()` directly starts the browser binary returned by the ChatUp resolver with a persistent Profile, unpacked extension, and loopback CDP. It exposes no Playwright Page/Locator API.
