# CLI Tree

`ChatPost 0.1.x` currently exposes only the browser-level login foundation: platform discovery, Profile discovery, and Zhihu `profiles/login/status/logout`. This PR does not register draft, publish, QR-artifact, account-helper, or publishing-adapter commands.

Here `PROFILE` is a registry alias / browser user-data directory / login-state container. It is not a Zhihu account ID, cookie, local storage, IndexedDB, session, or token.

## Current Commands

`chatpost --tree` prints the real registered CLI tree:

```text
chatpost  # browser-level platform login manager
├── --help  # Show help for the current command.
├── --version  # Show package version.
├── --tree  # Print the registered CLI tree with command purpose and IO shape.
├── platforms [--output text|json] [-I/--no-interactive]  # List supported platforms without starting a browser.
├── profiles [--platform zhihu] [--registry PATH] [--output text|json] [-I/--no-interactive]  # List configured browser Profiles without checking login state.
└── zhihu  # Zhihu browser login capabilities
    ├── profiles [--registry PATH] [--output text|json] [-I/--no-interactive]  # List configured Zhihu browser Profiles.
    ├── login PROFILE [--registry PATH] [--timeout INTEGER] [--output text|json] [-I/--no-interactive]  # Open/check a pure browser login session; emit page-owned login_url if needed.
    ├── status PROFILE [--registry PATH] [--output text|json] [-I/--no-interactive]  # Check Zhihu web login state from page-visible browser state only.
    └── logout PROFILE [--registry PATH] [--output text|json] [-I/--no-interactive]  # Log out or clear Zhihu browser state after browser-level status.
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
```

## Command Notes

- `chatpost platforms`: list supported platforms; does not start a browser, inspect login state, or touch any publishing adapter.
- `chatpost profiles [--platform zhihu]`: list configured browser Profiles from the registry; does not start a browser or inspect login state.
- `chatpost zhihu profiles`: list only Zhihu Profiles.
- `chatpost zhihu status PROFILE`: start/connect a controlled Chromium Profile and infer `LOGGED_IN`, `LOGGED_OUT`, or `UNKNOWN` from Zhihu page-visible DOM/URL/menu state only. It never reads or exports cookies, local storage, IndexedDB, sessions, or tokens.
- `chatpost zhihu login PROFILE`: run a browser-page status precheck; if already logged in, return `LOGGED_IN`; otherwise open the Zhihu login page, quickly emit a page-owned `login_url` or `browser_opened` handoff, then keep the browser alive while waiting for login.
- `chatpost zhihu logout PROFILE`: run browser-page status first; return `ALREADY_LOGGED_OUT` when logged out; clear Zhihu origins only after a logged-in precheck. Clearing state does not read session values.

## Login Runner Config

The login foundation only needs browser fields:

```toml
[zhihu]
playwright_version = "1.61.1"
playwright_home = "/absolute/path/to/.chatarch/playwright"
profile_dir = "/absolute/path/to/zhihu-profile"
cdp_host = "127.0.0.1"
cdp_port = 9227
headless = true
browser_args = ["--disable-dev-shm-usage"]
attach_existing_cdp = false
```

Safety boundary:

- `profile_dir` must exist and must not be group/other-accessible;
- CDP must bind the numeric IPv4 loopback `127.0.0.1`;
- `browser_args` cannot override Profile, CDP, or extension ownership arguments;
- registry/config/output never store cookies, local storage, IndexedDB, sessions, verification codes, phone numbers, passwords, or tokens.

## Explicitly Not in This CLI Surface

Account helpers, QR helpers, Zhihu account helpers, draft, verify, and doctor are not part of this login foundation and are not registered as current user-visible or hidden commands.

Future publishing, draft, or adapter-verification work must be designed in separate PRs and must not pollute the pure browser semantics of `login/status/logout`.
