# CLI Tree

`ChatPost 0.1.x` now exposes three capability layers:

1. Browser-level login foundation: platform discovery, Profile discovery, and Zhihu/XHS/CSDN `profiles/login/status/logout`.
2. Separate Wechatsync draft entrypoints: `chatpost zhihu draft PROFILE SOURCE` and `chatpost csdn draft PROFILE SOURCE` can dry-run or create one draft, and neither final-publishes.
3. XHS currently keeps only the QR login foundation; draft/publish remains outside the user-visible CLI.

Here `PROFILE` is a registry alias / browser user-data directory / login-state container. It is not a platform account ID, cookie, local storage, IndexedDB, session, or token. `draft` reuses the same Profile but must not change the pure browser semantics of `login/status/logout`.

## Current Commands

`chatpost --tree` prints the real registered CLI tree:

```text
chatpost  # browser-level platform login and draft manager
├── --help  # Show help for the current command.
├── --version  # Show package version.
├── --tree  # Print the registered CLI tree with command purpose and IO shape.
├── platforms [--output text|json] [-I/--no-interactive]  # List supported platforms without starting a browser.
├── profiles [--platform zhihu|xhs|csdn] [--registry PATH] [--output text|json] [-I/--no-interactive]  # List configured browser Profiles without checking login state.
├── zhihu  # Zhihu browser login and Wechatsync draft capabilities
    ├── profiles [--registry PATH] [--output text|json] [-I/--no-interactive]  # List configured Zhihu browser Profiles.
    ├── login PROFILE [--registry PATH] [--timeout INTEGER] [--output text|json] [-I/--no-interactive]  # Open/check a pure browser login session; emit page-owned login_url if needed.
    ├── status PROFILE [--registry PATH] [--output text|json] [-I/--no-interactive]  # Check Zhihu web login state from page-visible browser state only.
    ├── logout PROFILE [--registry PATH] [--output text|json] [-I/--no-interactive]  # Log out or clear Zhihu browser state after browser-level status.
    └── draft PROFILE SOURCE [--registry PATH] [--dry-run] [--receipt PATH] [--output text|json] [-I/--no-interactive]  # Dry-run or create one Zhihu draft through Wechatsync; never final-publish.
├── xhs  # XHS browser login system
    ├── profiles [--registry PATH] [--output text|json] [-I/--no-interactive]  # List configured XHS browser Profiles.
    ├── login PROFILE [--registry PATH] [--timeout INTEGER] [--qrcode PATH] [--output text|json] [-I/--no-interactive]  # Wait for the creator login page's own QR handoff and write the QR artifact.
    ├── status PROFILE [--registry PATH] [--output text|json] [-I/--no-interactive]  # Check XHS web login state from page-visible browser state only.
    └── logout PROFILE [--registry PATH] [--output text|json] [-I/--no-interactive]  # Log out or clear XHS browser state after browser-level status.
└── csdn  # CSDN browser login and Wechatsync draft capabilities
    ├── profiles [--registry PATH] [--output text|json] [-I/--no-interactive]  # List configured CSDN browser Profiles.
    ├── login PROFILE [--registry PATH] [--timeout INTEGER] [--qrcode PATH] [--output text|json] [-I/--no-interactive]  # Wait for the CSDN login page's own QR handoff and write the QR artifact.
    ├── status PROFILE [--registry PATH] [--output text|json] [-I/--no-interactive]  # Check CSDN web login state from page-visible browser state only.
    ├── logout PROFILE [--registry PATH] [--output text|json] [-I/--no-interactive]  # Log out or clear CSDN browser state after browser-level status.
    └── draft PROFILE SOURCE [--registry PATH] [--dry-run] [--receipt PATH] [--output text|json] [-I/--no-interactive]  # Dry-run or create one CSDN draft through Wechatsync; never final-publish.
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
chatpost xhs --help
chatpost xhs profiles --help
chatpost xhs login --help
chatpost xhs status --help
chatpost xhs logout --help
chatpost csdn --help
chatpost csdn profiles --help
chatpost csdn login --help
chatpost csdn status --help
chatpost csdn logout --help
chatpost csdn draft --help
```

## Command Notes

- `chatpost platforms`: list supported platforms; does not start a browser, inspect login state, or touch any publishing adapter.
- `chatpost profiles [--platform zhihu|xhs|csdn]`: list configured browser Profiles from the registry; does not start a browser or inspect login state.
- `chatpost <platform> profiles`: list only one platform's Profiles.
- `chatpost zhihu status PROFILE` / `chatpost xhs status PROFILE` / `chatpost csdn status PROFILE`: start/connect a controlled Chromium Profile and infer `LOGGED_IN`, `LOGGED_OUT`, or `UNKNOWN` from page-visible DOM/URL/menu state only. It never reads or exports cookies, local storage, IndexedDB, sessions, or tokens.
- `chatpost zhihu login PROFILE`: run a browser-page status precheck; if already logged in, return `LOGGED_IN`; otherwise open the Zhihu login page, quickly emit a page-owned `login_url` or `browser_opened` handoff, then keep the browser alive while waiting for login.
- `chatpost xhs login PROFILE --qrcode PATH`: run a browser-page status precheck; if already logged in, return `LOGGED_IN`; otherwise open the XHS creator login page, switch to QR login, write a mode-`0600` QR PNG, and emit only `qrcode_path`. User-visible output never exposes `login_url`, `loginconfirm`, raw data URLs, base64, or QR tokens.
- `chatpost csdn login PROFILE --qrcode PATH`: run a browser-page status precheck; if already logged in, return `LOGGED_IN`; otherwise open CSDN login, write a mode-`0600` QR PNG, and emit only `qrcode_path`. Password/SMS/CAPTCHA checkpoints stay in the human browser flow; the CLI does not bypass them, solve them, or store verification contents.
- `chatpost zhihu logout PROFILE` / `chatpost xhs logout PROFILE` / `chatpost csdn logout PROFILE`: run browser-page status first; return `ALREADY_LOGGED_OUT` when logged out; clear platform origins only after a logged-in precheck. Clearing state does not read session values.
- `chatpost zhihu draft PROFILE SOURCE --dry-run` / `chatpost csdn draft PROFILE SOURCE --dry-run`: parse the source through Wechatsync and return `DRY_RUN_OK`/preview without starting a browser or writing a draft.
- `chatpost zhihu draft PROFILE SOURCE --receipt PATH` / `chatpost csdn draft PROFILE SOURCE --receipt PATH`: start the configured browser/Profile/extension/bridge, create one draft through Wechatsync, write a mode `0600` receipt, and return `DRAFT_CREATED`, `draft_id`, and a review URL. It never clicks final publish.

## Login Runner Config

The login foundation only needs browser fields. Zhihu, XHS, and CSDN use the same shape with different table names:

```toml
[csdn]
playwright_version = "1.61.1"
playwright_home = "/absolute/path/to/.chatarch/playwright"
profile_dir = "/absolute/path/to/csdn-profile"
cdp_host = "127.0.0.1"
cdp_port = 9284
headless = true
browser_args = ["--disable-dev-shm-usage"]
attach_existing_cdp = false
```

## Draft Runner Config

Zhihu and CSDN `draft` need the full runner fields: browser/Profile fields plus extension, Node, Wechatsync CLI, private env file, and bridge loopback port. XHS currently has no user-visible draft/create command; `xhs login/status/logout` read only `[xhs]` browser fields and do not read adapter tokens or connect a publishing extension.

Safety boundary:

- `profile_dir` must exist and must not be group/other-accessible;
- CDP and bridge must bind the numeric IPv4 loopback `127.0.0.1`;
- `browser_args` cannot override Profile, CDP, or extension ownership arguments;
- registry/config/output never store cookies, local storage, IndexedDB, sessions, verification codes, phone numbers, passwords, or tokens;
- Zhihu/CSDN `draft create` only creates a draft. If the result is `RESULT_UNKNOWN`, the receipt preserves evidence and callers must not retry automatically;
- the current Wechatsync CSDN adapter capability is `draft`: its request uses `pubStatus="draft"`, and ChatPost has no callable public `post/publish` path for CSDN;
- XHS draft/publish is not in the current user-visible CLI; if a later adapter is added, it needs a separate command surface and must not write remotely from `login/status/logout`.

## Still Not in This CLI Surface

Account helpers, QR helpers, platform account helpers, verify, doctor, XHS draft/create, same-ID updates, and final public publishing are not current user-visible commands.

Future adapter verify/doctor, same-ID update, or final public publishing work should be handled in separate PRs and must not pollute the pure browser semantics of `login/status/logout`.
