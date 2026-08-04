# Python Interface Tree

The CLI only parses arguments. Substantive behavior lives in `chatpost.zhihu`.

```text
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

## ChatUp Dependency

```python
from chatup.playwright import PlaywrightBrowserInstallation, resolve
```

ChatPost resolves an existing exact Playwright browser installation. It never installs or upgrades one implicitly.

## Example

```python
from chatpost.zhihu import execute_task, load_runner_config, preflight

config = load_runner_config("runner.toml")
status = preflight(config)
result = execute_task(config, "article.md", mode="dry-run")
```

`execute_task(..., mode="create")` is an external write. Callers must retain its receipt and stop automatic retries after `ResultUnknownError` until the Zhihu draft box is reconciled.

`browser_session()` directly starts the browser binary returned by the ChatUp resolver with a persistent Profile, unpacked extension, and loopback CDP. It exposes no Playwright Page/Locator API.
