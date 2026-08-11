# ChatPost Documentation

ChatPost's current user-visible focus is the **pure browser login foundation plus separate Wechatsync draft entrypoints**: discover platforms, discover Profiles, check Zhihu/XHS/CSDN web login state, open a login handoff, log out / clear state, and create Zhihu or CSDN drafts through Wechatsync. XHS currently provides QR-image login handoff only, with no draft/publish command.

| Scenario | Document |
| --- | --- |
| Run Zhihu/CSDN login and draft flows now | [Quickstart: Logical Profiles, Zhihu/CSDN Login, and Drafts](quickstart.en.md) |
| Inspect the real CLI tree | [CLI Tree](cli-tree.en.md) |
| Check implemented capabilities and boundaries | [Capability Map](capability-map.en.md) |
| Understand overall resources and flow | [Overall Architecture](architecture.en.md) |
| Review Chrome installation, Profile, and state boundaries | [Configuration, Environment, and State](configuration.en.md) |
| Use package APIs from Python | [Python Interface Tree](interface-tree.en.md) |

## Current Stable Entrypoints

```bash
chatpost --tree
chatpost platforms
chatpost profiles --platform zhihu
chatpost profiles --platform xhs
chatpost profiles --platform csdn
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
chatpost csdn profiles
chatpost csdn status PROFILE
chatpost csdn login PROFILE --qrcode PATH
chatpost csdn logout PROFILE
chatpost csdn draft PROFILE SOURCE --dry-run
chatpost csdn draft PROFILE SOURCE --receipt PATH
```

The default registry is `~/.chatarch/chatpost/accounts.toml` (override explicitly with `CHATPOST_ACCOUNT_REGISTRY` or `--registry PATH`). `login/status/logout` are browser-level only: no publishing adapter, no publishing extension, no publishing token, and no reading/exporting cookies/local storage/IndexedDB/sessions/tokens. `chatpost zhihu draft` and `chatpost csdn draft` are separate Wechatsync adapter entrypoints: dry-run uses the CLI parser for preview, while create uses the extension MCP direct bridge to create one draft and never final-publishes. The current CSDN adapter returns `draftOnly=true`; public `post/publish` is not a current ChatPost CLI capability. XHS currently exposes only `profiles/login/status/logout`; `login` writes a QR artifact and emits only `qrcode_path`, without exposing the short-lived confirmation link or QR token as a user interface.
