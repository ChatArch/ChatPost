# CLI Tree

`ChatPost 0.1.x` now exposes two capability layers:

1. Browser-level login foundation: platform discovery, Profile discovery, and Zhihu/Xiaohongshu `profiles/login/status/logout`.
2. Separate draft entrypoints: `chatpost zhihu draft PROFILE SOURCE` can dry-run or create one Zhihu draft through Wechatsync; `chatpost xiaohongshu draft PROFILE SOURCE` currently performs local dry-run/source validation only, and create explicitly returns unsupported until a Xiaohongshu adapter is connected.

Here `PROFILE` is a registry alias / browser user-data directory / login-state container. It is not a platform account ID, cookie, local storage, IndexedDB, session, or token. `draft` reuses the same Profile but must not change the pure browser semantics of `login/status/logout`.

## Current Commands

`chatpost --tree` prints the real registered CLI tree:

```text
chatpost  # browser-level platform login and draft manager
├── --help  # Show help for the current command.
├── --version  # Show package version.
├── --tree  # Print the registered CLI tree with command purpose and IO shape.
├── platforms [--output text|json] [-I/--no-interactive]  # List supported platforms without starting a browser.
├── profiles [--platform zhihu|xiaohongshu] [--registry PATH] [--output text|json] [-I/--no-interactive]  # List configured browser Profiles without checking login state.
├── zhihu  # Zhihu browser login and Wechatsync draft capabilities
    ├── profiles [--registry PATH] [--output text|json] [-I/--no-interactive]  # List configured Zhihu browser Profiles.
    ├── login PROFILE [--registry PATH] [--timeout INTEGER] [--output text|json] [-I/--no-interactive]  # Open/check a pure browser login session; emit page-owned login_url if needed.
    ├── status PROFILE [--registry PATH] [--output text|json] [-I/--no-interactive]  # Check Zhihu web login state from page-visible browser state only.
    ├── logout PROFILE [--registry PATH] [--output text|json] [-I/--no-interactive]  # Log out or clear Zhihu browser state after browser-level status.
    └── draft PROFILE SOURCE [--registry PATH] [--dry-run] [--receipt PATH] [--output text|json] [-I/--no-interactive]  # Dry-run or create one Zhihu draft through Wechatsync; never final-publish.
└── xiaohongshu  # Xiaohongshu browser login and draft boundary
    ├── profiles [--registry PATH] [--output text|json] [-I/--no-interactive]  # List configured Xiaohongshu browser Profiles.
    ├── login PROFILE [--registry PATH] [--timeout INTEGER] [--output text|json] [-I/--no-interactive]  # Open/check a pure browser login session; emit page-owned login_url if needed.
    ├── status PROFILE [--registry PATH] [--output text|json] [-I/--no-interactive]  # Check Xiaohongshu web login state from page-visible browser state only.
    ├── logout PROFILE [--registry PATH] [--output text|json] [-I/--no-interactive]  # Log out or clear Xiaohongshu browser state after browser-level status.
    └── draft PROFILE SOURCE [--registry PATH] [--dry-run] [--receipt PATH] [--output text|json] [-I/--no-interactive]  # Dry-run local source validation; create is unsupported until a Xiaohongshu adapter is connected.
```

Inspect real help:

```bash
chatpost --tree
chatpost --help
chatpost platforms --help
chatpost profiles --help
chatpost zhihu --help
chatpost zhihu profiles --help
chatpost zhihu login --help
chatpost zhihu status --help
chatpost zhihu logout --help
chatpost zhihu draft --help
chatpost xiaohongshu --help
chatpost xiaohongshu profiles --help
chatpost xiaohongshu login --help
chatpost xiaohongshu status --help
chatpost xiaohongshu logout --help
chatpost xiaohongshu draft --help
```

## Command Notes

- `chatpost platforms`: list supported platforms; does not start a browser, inspect login state, or touch any publishing adapter.
- `chatpost profiles [--platform zhihu|xiaohongshu]`: list configured browser Profiles from the registry; does not start a browser or inspect login state.
- `chatpost zhihu profiles` / `chatpost xiaohongshu profiles`: list only one platform's Profiles.
- `chatpost zhihu status PROFILE` / `chatpost xiaohongshu status PROFILE`: start/connect a controlled Chromium Profile and infer `LOGGED_IN`, `LOGGED_OUT`, or `UNKNOWN` from page-visible DOM/URL/menu state only. It never reads or exports cookies, local storage, IndexedDB, sessions, or tokens.
- `chatpost zhihu login PROFILE` / `chatpost xiaohongshu login PROFILE`: run a browser-page status precheck; if already logged in, return `LOGGED_IN`; otherwise open the platform login/home page, quickly emit a page-owned `login_url` or `browser_opened` handoff, then keep the browser alive while waiting for login. Xiaohongshu network-risk blocks return `LOGIN_BLOCKED` / `block_reason=network_risk` instead of pretending that a fallback login page is a QR URL.
- `chatpost zhihu logout PROFILE` / `chatpost xiaohongshu logout PROFILE`: run browser-page status first; return `ALREADY_LOGGED_OUT` when logged out; clear platform origins only after a logged-in precheck. Clearing state does not read session values.
- `chatpost zhihu draft PROFILE SOURCE --dry-run`: parse the source through Wechatsync and return `DRY_RUN_OK`/preview without starting a browser or writing a draft.
- `chatpost zhihu draft PROFILE SOURCE --receipt PATH`: start the configured browser/Profile/extension/bridge, create exactly one Zhihu draft through Wechatsync, write a mode `0600` receipt, and return `DRAFT_CREATED`, `draft_id`, and the `/edit` review URL. It never clicks final publish.
- `chatpost xiaohongshu draft PROFILE SOURCE --dry-run`: perform local source reading, hashing, and preview validation only.
- `chatpost xiaohongshu draft PROFILE SOURCE --receipt PATH`: explicitly fails with `CREATE_NOT_SUPPORTED` and writes a mode `0600` receipt. It does not attempt a remote write or fake a draft success.

## Login Runner Config

The login foundation only needs browser fields. Zhihu and Xiaohongshu use the same shape with different table names:

```toml
[xiaohongshu]
playwright_version = "1.61.1"
playwright_home = "/absolute/path/to/.chatarch/playwright"
profile_dir = "/absolute/path/to/xiaohongshu-profile"
cdp_host = "127.0.0.1"
cdp_port = 9237
headless = true
browser_args = ["--disable-dev-shm-usage"]
attach_existing_cdp = false
```

## Draft Runner Config

Zhihu `draft` needs the full runner fields: browser/Profile fields plus extension, Node, Wechatsync CLI, private env file, and bridge loopback port. Xiaohongshu `draft` currently reads only `[xiaohongshu]` browser fields for local validation / receipts; it does not read adapter tokens or connect a publishing extension.

Safety boundary:

- `profile_dir` must exist and must not be group/other-accessible;
- CDP and bridge must bind the numeric IPv4 loopback `127.0.0.1`;
- `browser_args` cannot override Profile, CDP, or extension ownership arguments;
- registry/config/output never store cookies, local storage, IndexedDB, sessions, verification codes, phone numbers, passwords, or tokens;
- Zhihu `draft create` only creates a draft. If the result is `RESULT_UNKNOWN`, the receipt preserves evidence and callers must not retry automatically;
- until a Xiaohongshu create adapter is connected, create returns `CREATE_NOT_SUPPORTED` and performs no remote write.

## Still Not in This CLI Surface

Account helpers, QR helpers, platform account helpers, verify, doctor, same-ID updates, and final publish are not current user-visible commands.

Future adapter verify/doctor, same-ID update, or final publish work should be handled in separate PRs and must not pollute the pure browser semantics of `login/status/logout`.
