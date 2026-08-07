# ChatPost Documentation

ChatPost's current user-visible focus is the **pure browser login foundation**: discover platforms, discover Profiles, check Zhihu web login state, open a login handoff, and log out / clear state.

| Scenario | Document |
| --- | --- |
| Run the login foundation now | [Quickstart: Pure Browser Login](quickstart.md) |
| Inspect the real CLI tree | [CLI Tree](cli-tree.md) |
| Check implemented capabilities and boundaries | [Capability Map](capability-map.md) |
| Understand overall resources and flow | [Overall Architecture](architecture.md) |
| Review Chrome installation, Profile, and state boundaries | [Configuration, Environment, and State](configuration.md) |
| Use package APIs from Python | [Python Interface Tree](interface-tree.md) |

## Current Stable Entrypoints

```bash
chatpost --tree
chatpost platforms
chatpost profiles --platform zhihu --registry accounts.toml
chatpost zhihu profiles --registry accounts.toml
chatpost zhihu status PROFILE --registry accounts.toml
chatpost zhihu login PROFILE --registry accounts.toml
chatpost zhihu logout PROFILE --registry accounts.toml
```

`login/status/logout` are browser-level only: no publishing adapter, no publishing extension, no publishing token, and no reading/exporting cookies/local storage/IndexedDB/sessions/tokens.
