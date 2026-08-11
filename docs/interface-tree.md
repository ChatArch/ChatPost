# Python 接口树

命令行只做参数解析；实质能力位于 `chatpost.accounts`、`chatpost.zhihu`、`chatpost.xhs` 和 `chatpost.csdn`。

```text
chatpost.accounts
├── Account
├── AccountRegistryError
├── default_chatpost_home()       # 默认 ~/.chatarch/chatpost，可由 CHATPOST_HOME 覆盖
├── default_registry_path()       # 默认 ~/.chatarch/chatpost/accounts.toml，可由 CHATPOST_ACCOUNT_REGISTRY 覆盖
├── load_accounts(path=None)
└── resolve_account(target, accounts)

chatpost.zhihu
├── ZhihuBrowserConfig            # 纯浏览器登录配置；可记录 browser_profile
├── load_browser_config(path)     # 不读取 adapter/env/extension 字段
├── browser_status(config)
├── browser_login(config, timeout=..., event_callback=...)
├── browser_logout(config)
├── browser_login_session(config)
├── ZhihuRunnerConfig             # draft/Wechatsync runner 配置边界；可引用 browser_profile
├── load_runner_config(path)      # draft runner 专用；不得被 login/status/logout 默认调用
├── execute_task(config, source, mode="dry-run"|"create")
└── ResultUnknownError            # create 结果不确定时禁止自动重试

chatpost.csdn
├── CSDNBrowserConfig             # 纯浏览器登录配置；可记录 browser_profile
├── load_browser_config(path)     # 不读取 adapter/env/extension 字段
├── browser_status(config)
├── browser_login(config, timeout=..., qrcode_path=..., event_callback=...)
├── browser_logout(config)
├── browser_login_session(config)
├── CSDNRunnerConfig              # draft/Wechatsync runner 配置边界；可引用 browser_profile
├── load_runner_config(path)      # draft runner 专用；不得被 login/status/logout 默认调用
└── execute_task(config, source, mode="dry-run"|"create")
```

## ChatUp / ChatBrowser dependency

```python
from chatup.playwright import resolve
from chatbrowser.registry import profile_path
```

ChatPost 只解析已存在的 exact Playwright browser installation，不隐式安装或升级。ChatBrowser 负责浏览器 runtime、Profile metadata 和 CDP session metadata 的安全边界；ChatPost 不保存 Cookie、LocalStorage、IndexedDB、session、token 或 QR payload。配置文件可写 `browser_profile = "zhihu-test"` / `browser_profile = "csdn-test"`，`load_browser_config()` / `load_runner_config()` 会通过 `chatbrowser.registry.profile_path()` 解析 Profile 路径；若同时写 `profile_dir`，它必须与 ChatBrowser registry 记录一致。

## 示例：默认 ChatArch state root 读取 Profile registry

```python
from chatpost.accounts import default_registry_path, load_accounts, resolve_account
from chatpost.csdn import browser_status, load_browser_config

registry_path = default_registry_path()  # ~/.chatarch/chatpost/accounts.toml
accounts = load_accounts(registry_path)
account = resolve_account("csdn-test", accounts)
config = load_browser_config(account.runner_config)
status = browser_status(config)
```

默认状态根目录是 `~/.chatarch/chatpost/`。任务实验可以显式传 `load_accounts(path)` 或 CLI `--registry PATH`，但普通用户默认不需要在仓库根目录或当前目录放 `accounts.toml`。

## Wechatsync 接入边界

`ZhihuRunnerConfig` / `CSDNRunnerConfig`、`load_runner_config()` 和 `execute_task()` 是 `chatpost zhihu draft` / `chatpost csdn draft` 的 adapter 层入口。它们可以包含 extension、bridge、env 和 adapter CLI 字段；但 `browser_status()`、`browser_login()` 和 `browser_logout()` 必须继续使用对应的 browser config，不能为了 draft 接入重新依赖 Wechatsync、发布 token、Cookie、LocalStorage 或 IndexedDB。

CSDN draft 的平台参数固定为 `csdn`，并且只接受 Wechatsync 返回的 `draftOnly=true` 草稿结果。ChatPost 当前没有 CSDN 公开 `post/publish` Python API。
