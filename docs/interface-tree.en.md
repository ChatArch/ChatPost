# Python Interface Tree

The CLI only parses arguments. Substantive behavior lives in `chatpost.accounts` and `chatpost.zhihu`.

```text
chatpost.accounts
├── Account
├── AccountRegistryError
├── default_chatpost_home()       # defaults to ~/.chatarch/chatpost, override with CHATPOST_HOME
├── default_registry_path()       # defaults to ~/.chatarch/chatpost/accounts.toml, override with CHATPOST_ACCOUNT_REGISTRY
├── load_accounts(path=None)
└── resolve_account(target, accounts)

chatpost.zhihu
├── ZhihuBrowserConfig            # pure browser-login config
├── load_browser_config(path)     # ignores adapter/env/extension fields
├── browser_preflight(config)
├── browser_status(config)
├── browser_login(config, timeout=..., event_callback=...)
├── browser_logout(config)
├── browser_login_session(config)
├── ZhihuRunnerConfig             # draft / Wechatsync runner boundary
├── load_runner_config(path)      # draft-runner only; not the default login/status/logout path
├── execute_task(config, source, mode="dry-run"|"create")
└── ResultUnknownError            # forbids automatic retry after ambiguous create results
```

## ChatUp / ChatBrowser Dependency

```python
from chatup.playwright import resolve
import chatbrowser
```

ChatPost resolves an existing exact Playwright browser installation. It never installs or upgrades one implicitly. ChatBrowser owns the browser runtime, Profile metadata, and CDP session metadata safety boundary; ChatPost does not store cookies, local storage, IndexedDB, sessions, tokens, or QR payloads.

## Example: Read Profiles From The Default ChatArch State Root

```python
from chatpost.accounts import default_registry_path, load_accounts, resolve_account
from chatpost.zhihu import browser_status, load_browser_config

registry_path = default_registry_path()  # ~/.chatarch/chatpost/accounts.toml
accounts = load_accounts(registry_path)
account = resolve_account("zhihu@zhihu-personal", accounts)
config = load_browser_config(account.runner_config)
status = browser_status(config)
```

The default state root is `~/.chatarch/chatpost/`. Task-local experiments may pass `load_accounts(path)` or CLI `--registry PATH`, but normal users do not need to keep `accounts.toml` in the repository root or current working directory.

## Wechatsync Integration Boundary

`ZhihuRunnerConfig` / `load_runner_config()` / `execute_task()` are the adapter-layer entrypoints behind `chatpost zhihu draft`. They may contain extension, bridge, env, and adapter CLI fields; however `browser_status()`, `browser_login()`, and `browser_logout()` must keep using `ZhihuBrowserConfig` and must not regain a dependency on Wechatsync, publishing tokens, cookies, local storage, or IndexedDB.