# ChatPost Documentation

ChatPost's current user-visible focus is the **pure browser login foundation plus a separate Zhihu draft entrypoint**: discover platforms, discover Profiles, check Zhihu/XHS web login state, open a login handoff, log out / clear state, create Zhihu drafts through Wechatsync, and provide a XHS QR-image login handoff.

| Scenario | Document |
| --- | --- |
| Run login and Zhihu draft flows now | [Quickstart: Browser Login, Zhihu Drafts, and XHS QR Login](quickstart.md) |
| Inspect the real CLI tree | [CLI Tree](cli-tree.md) |
| Check implemented capabilities and boundaries | [Capability Map](capability-map.md) |
| Understand overall resources and flow | [Overall Architecture](architecture.md) |
| Review Chrome installation, Profile, and state boundaries | [Configuration, Environment, and State](configuration.md) |
| Use package APIs from Python | [Python Interface Tree](interface-tree.md) |

## Current Stable Entrypoints

```bash
chatpost --tree
chatpost platforms
chatpost profiles --platform zhihu
chatpost profiles --platform xhs
chatpost zhihu profiles
chatpost zhihu status PROFILE
chatpost zhihu login PROFILE
chatpost zhihu logout PROFILE
chatpost zhihu draft PROFILE SOURCE --dry-run
chatpost zhihu draft PROFILE SOURCE --receipt PATH
chatpost xhs profiles
chatpost xhs status PROFILE
chatpost xhs login PROFILE --qrcode PATH
chatpost xhs logout PROFILE
```

The default registry is `~/.chatarch/chatpost/accounts.toml` (override explicitly with `CHATPOST_ACCOUNT_REGISTRY` or `--registry PATH`). `login/status/logout` are browser-level only: no publishing adapter, no publishing extension, no publishing token, and no reading/exporting cookies/local storage/IndexedDB/sessions/tokens. `chatpost zhihu draft` is a separate Wechatsync adapter entrypoint: dry-run uses the CLI parser for preview, while create uses the extension MCP direct bridge to create one draft and never final-publishes. XHS currently exposes only `profiles/login/status/logout`; `login` writes a QR artifact and emits only `qrcode_path`, without exposing the short-lived confirmation link or QR token as a user interface.
