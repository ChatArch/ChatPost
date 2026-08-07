# CLI Tree

`ChatPost 0.1.x` now organizes the user-visible command surface as “discovery entrypoints plus platform-specific capabilities.” The top level exposes only platform discovery, Profile discovery, and concrete platform names. Zhihu login, logout, status, and drafts live under `chatpost zhihu ...`, so there is no global `chatpost login` or `chatpost post` surface.

Here `profile` means a non-sensitive Chrome/Profile target configuration: it binds alias, platform, runner_config, profile name, and label so `login/status/logout/draft` can find the right browser Profile. It is not cookies, local storage, Zhihu account details, or credentials.

## Current Commands

`chatpost --tree` prints the registered CLI tree with each leaf's shape, purpose, and output boundary:

```text
chatpost  # platform content publishing and draft orchestration
├── --help  # Show help for the current command.
├── --version  # Show package version.
├── --tree  # Print the registered CLI tree with command purpose and IO shape.
├── platforms [--output text|json] [-I/--no-interactive]  # List supported publishing platforms.
├── profiles [--platform zhihu] [--registry PATH] [--output text|json] [-I/--no-interactive]  # List configured Chrome/profile targets.
└── zhihu  # Zhihu platform capabilities
    ├── profiles [--registry PATH] [--output text|json] [-I/--no-interactive]  # List configured Zhihu Chrome/profile targets.
    ├── login PROFILE [--registry PATH] [--qr PATH] [--receipt PATH] [--timeout INTEGER] [--output text|json] [-I/--no-interactive]  # Open live QR login, emit link/QR/receipt, and wait for READY.
    ├── logout PROFILE [--registry PATH] [--output text|json] [-I/--no-interactive]  # Clear Zhihu login state for this profile; does not read session values.
    ├── status PROFILE [--registry PATH] [--output text|json] [-I/--no-interactive]  # Read-only Zhihu auth check.
    └── draft  # Zhihu review-draft operations
        ├── dry-run PROFILE SOURCE [--registry PATH] [--output text|json] [-I/--no-interactive]  # Parse SOURCE without starting browser or writing Zhihu.
        └── create PROFILE SOURCE [--registry PATH] --receipt PATH [--output text|json] [-I/--no-interactive]  # Create exactly one Zhihu review draft.
```

Inspect the real help:

```bash
chatpost --tree
chatpost --help
chatpost platforms --help
chatpost profiles --help
chatpost zhihu --help
chatpost zhihu profiles --help
chatpost zhihu login --help
chatpost zhihu logout --help
chatpost zhihu status --help
chatpost zhihu draft --help
```

## Common Task Order

Create a Profile registry that contains only non-sensitive metadata:

```toml
[accounts."zhihu-test"]
platform = "zhihu"
runner_config = "/absolute/path/to/runner.toml"
profile = "zhihu-test"
label = "Zhihu test account"
```

Then use the visible platform entrypoints:

```bash
chatpost platforms \
  --output json \
  -I

chatpost zhihu profiles \
  --registry accounts.toml \
  --output json \
  -I

chatpost zhihu login zhihu-test \
  --registry accounts.toml \
  --qr live-login-qr.png \
  --receipt live-login-qr-ready.json \
  --timeout 900 \
  --output json \
  -I

chatpost zhihu status zhihu-test \
  --registry accounts.toml \
  --output json \
  -I

chatpost zhihu logout zhihu-test \
  --registry accounts.toml \
  --output json \
  -I

chatpost zhihu draft dry-run zhihu-test article.md \
  --registry accounts.toml \
  --output json \
  -I

chatpost zhihu draft create zhihu-test article.md \
  --registry accounts.toml \
  --receipt receipt.json \
  --output json \
  -I
```

These entrypoints are ChatPost orchestration only:

1. `platforms` lists first-class platforms and recommended entrypoints.
2. `profiles` / `zhihu profiles` read only the Profile registry. They do not store or print cookies, local storage, tokens, passwords, credentials, or other secrets.
3. `zhihu login` is a QR login handoff: it opens the Zhihu login page in the same browser Profile, waits until the page QR is scannable, renders the **same login page's page-owned `login_url`** into a QR image/writes a mode-`0600` receipt, then keeps the browser open until the Profile becomes `READY`. The browser/Profile still owns login state and ChatPost never exports cookies.
4. `zhihu status` resolves `PROFILE` and runs one read-only Zhihu auth check without reading cookies, local storage, or IndexedDB.
5. `zhihu logout` clears Zhihu origin login state for that Profile. It sends browser storage-clear commands but does not read or export session values.
6. `zhihu draft dry-run` parses the article without starting a browser, connecting the extension, or writing to Zhihu.
7. `zhihu draft create` invokes the Wechatsync create path exactly once. Success writes a mode-`0600` receipt. An ambiguous result writes `RESULT_UNKNOWN` and must never be retried automatically. It creates a review draft, not final publish.
8. Phone numbers and verification codes are human browser-flow inputs only. ChatPost does not expose `--phone`, `--code`, `--otp`, or `--sms-code`, and never writes those values to the registry, config, receipt, or logs.

`ChatPost 0.1.x` has **no final-publish command** and no article-update command.

## Hidden compatibility

Older script entrypoints remain callable, but are not shown in `--help` or `--tree`:

```text
chatpost account list/show
chatpost qr encode
chatpost zhihu account status/preflight/login qr/login qr-artifact/login code
```

These hidden compatibility commands exist for older automation, not for the new daily-use docs path. Platform delivery remains the host/gateway's responsibility, and ChatPost CLI does not output `MEDIA:ssh://...` or `[media attachment]`.

## ChatUp / ChatBrowser Boundary

Prepare machine-level artifacts explicitly through ChatUp:

```bash
chatup nodejs -I
chatup playwright install 1.61.1 --browser chromium --output json -I
chatup playwright doctor 1.61.1 --browser chromium --output json -I
```

ChatPost depends on `chatup>=0.2.4,<0.3.0`, `chatbrowser>=0.1.2,<0.2.0`, and `qrcode[pil]>=7.4,<9.0`. The current Zhihu draft route still resolves the exact browser through ChatUp, then ChatPost owns the Profile, extension, loopback CDP/bridge, QR/link handoff artifacts, and Wechatsync process. The Profile registry stores only non-sensitive alias metadata. ChatBrowser owns the browser runtime, Profile metadata, and CDP session metadata safety boundary; richer session discovery should come through ChatBrowser rather than storing browser secrets in ChatPost.

```python
from chatup.playwright import resolve

installation = resolve("1.61.1", browser="chromium")
```

Ownership:

- ChatUp: the Playwright package, its declared browser revision, installation metadata, and executable path;
- ChatBrowser: browser runtime, Profile metadata, and CDP session metadata;
- ChatPost: Profile aliases, QR image artifacts, publishing task orchestration, Profile/extension/CDP/bridge/Wechatsync one-shot tasks, and receipts;
- Wechatsync: the Zhihu adapter and draft write;
- human: first login and final publication approval.

Playwright is an **installation and resolution substrate** here. The proven route still launches the resolved browser binary directly and wakes the extension over raw CDP. It does not use Playwright `Page`, Locator, or `launchPersistentContext()` APIs.

## Secret-Free Runner Configuration

```toml
[zhihu]
playwright_version = "1.61.1"
playwright_home = "/absolute/path/to/.chatarch/playwright"
profile_dir = "/absolute/path/to/zhihu-profile"
extension_dir = "/absolute/path/to/Wechatsync/packages/extension/dist"
node_bin = "/absolute/path/to/node"
wechatsync_cli = "/absolute/path/to/Wechatsync/packages/cli/dist/index.js"
env_file = "/absolute/path/to/chatpost-zhihu.env"
cdp_host = "127.0.0.1"
cdp_port = 9227
bridge_host = "127.0.0.1"
bridge_port = 9527
extension_id = "dipgimoobbhdefncjomgehikkbaklgii"
headless = true
browser_args = ["--disable-dev-shm-usage"]
attach_existing_cdp = false
```

Safety constraints:

- `profile_dir` must exist and must not be accessible by group or other users;
- `env_file` must be mode `0600` or stricter and contain `WECHATSYNC_TOKEN`;
- CDP and bridge hosts must be loopback;
- `browser_args` cannot override Profile, CDP, or extension ownership arguments;
- the config stores paths and non-secret values, never cookies, local storage, or Zhihu credentials.

## Commands That Remain Proposed

These resource boundaries remain useful, but the commands are not implemented:

```text
runner add|start|status|doctor|stop
publication list|show|retry
article update
post publish
```

Until implementation and tests exist, they must remain explicitly marked as proposals and stay out of executable Quick Starts.
