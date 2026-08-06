# CLI Tree

`ChatPost 0.1.x` now organizes commands as “platform-neutral capabilities plus platform-specific capabilities.” Top-level commands only expose the account alias registry, generic QR artifacts, and concrete platform names. Login, drafts, and platform runners live under their platform, so there is no global `chatpost login` or `chatpost post` surface.

## Current Commands

`chatpost --tree` prints the registered CLI tree with each leaf's shape, purpose, and output boundary:

```text
chatpost  # platform content publishing and draft orchestration
├── --help  # Show help for the current command.
├── --version  # Show package version.
├── --tree  # Print the registered CLI tree with command purpose and IO shape.
├── account  # account alias registry; metadata only
│   ├── list [--registry PATH] [--output text|json] [-I/--no-interactive]  # List account aliases; never reads cookies/tokens/session.
│   └── show TARGET [--registry PATH] [--output text|json] [-I/--no-interactive]  # Show one account alias by ALIAS or PLATFORM@ALIAS.
├── qr  # platform-neutral QR artifact tools
│   └── encode DATA --artifact PATH [--output text|json] [-I/--no-interactive]  # Render DATA into PNG without echoing DATA by default.
└── zhihu  # Zhihu platform capabilities
    ├── account  # Zhihu account status, preflight, and login checkpoints
    │   ├── status TARGET [--registry PATH] [--output text|json] [-I/--no-interactive]  # Read-only Zhihu auth check.
    │   ├── preflight TARGET [--registry PATH] [--output text|json] [-I/--no-interactive]  # Check runner/profile/browser/extension readiness.
    │   └── login  # Zhihu manual login checkpoints; no phone/code/cookie arguments.
    │       ├── qr TARGET [--registry PATH] [--timeout INTEGER] [--output text|json] [-I/--no-interactive]  # Open QR login checkpoint and wait for READY.
    │       ├── qr-artifact TARGET [--registry PATH] --artifact PATH --receipt PATH [--timeout INTEGER] [--output text|json] [-I/--no-interactive]  # Create live QR PNG + receipt, return immediately.
    │       └── code TARGET [--registry PATH] [--timeout INTEGER] [--output text|json] [-I/--no-interactive]  # Open SMS-code checkpoint without accepting phone/code values.
    └── draft  # Zhihu review-draft operations
        ├── dry-run TARGET SOURCE [--registry PATH] [--output text|json] [-I/--no-interactive]  # Parse SOURCE without starting browser or writing Zhihu.
        └── create TARGET SOURCE [--registry PATH] --receipt PATH [--output text|json] [-I/--no-interactive]  # Create exactly one Zhihu review draft.
```

Inspect the real help:

```bash
chatpost --tree
chatpost --help
chatpost account --help
chatpost qr --help
chatpost zhihu --help
chatpost zhihu account --help
chatpost zhihu account login --help
chatpost zhihu draft --help
```

## Common Task Order

Create a registry that contains only non-sensitive metadata:

```toml
[accounts."zhihu-test"]
platform = "zhihu"
runner_config = "/absolute/path/to/runner.toml"
profile = "zhihu-test"
label = "Zhihu test account"
```

Then use the platform-scoped entrypoints:

```bash
chatpost account list \
  --registry accounts.toml \
  --output json \
  -I

chatpost account show zhihu@zhihu-test \
  --registry accounts.toml \
  --output json \
  -I

chatpost qr encode 'https://www.zhihu.com/signin?login_method=qr' \
  --artifact login-url.png \
  --output json \
  -I

chatpost zhihu account status zhihu@zhihu-test \
  --registry accounts.toml \
  --output json \
  -I

chatpost zhihu account preflight zhihu@zhihu-test \
  --registry accounts.toml \
  --output json \
  -I

chatpost zhihu account login qr zhihu@zhihu-test \
  --registry accounts.toml \
  --timeout 900 \
  --output json \
  -I

chatpost zhihu account login qr-artifact zhihu@zhihu-test \
  --registry accounts.toml \
  --artifact live-login-qr.png \
  --receipt live-login-qr-ready.json \
  --timeout 60 \
  --output json \
  -I

chatpost zhihu account login code zhihu@zhihu-test \
  --registry accounts.toml \
  --timeout 900 \
  --output json \
  -I

chatpost zhihu draft dry-run zhihu@zhihu-test article.md \
  --registry accounts.toml \
  --output json \
  -I

chatpost zhihu draft create zhihu@zhihu-test article.md \
  --registry accounts.toml \
  --receipt receipt.json \
  --output json \
  -I
```

These entrypoints are ChatPost orchestration only:

1. `account list/show` read only the account alias registry. They do not store or print cookies, local storage, tokens, passwords, credentials, or other secrets.
2. `qr encode` renders caller-provided data into a PNG artifact and reports only artifact metadata by default.
3. `zhihu account status` resolves `platform@alias` and runs one read-only Zhihu auth check.
4. `zhihu account preflight` checks the exact Playwright install, Profile permissions, extension, Node, Wechatsync CLI, secret file, and loopback ports. It does not install, launch, or write to Zhihu.
5. `zhihu account login qr` opens the QR login checkpoint and waits until the account becomes `READY`; the browser/Profile still owns login state and ChatPost never exports cookies.
6. `zhihu account login qr-artifact` opens the live login checkpoint, creates a fresh Zhihu scan-login link in the browser context, renders the extracted `login_url` as a QR PNG, writes a mode-`0600` receipt, and returns immediately. The conversation host decides how to deliver the image.
7. `zhihu account login code` opens an SMS-code checkpoint and waits for `READY`; phone numbers and verification codes are used only in the human browser flow, never as CLI arguments and never in the registry, config, receipt, or logs.
8. `zhihu draft dry-run` parses the article without starting a browser, connecting the extension, or writing to Zhihu.
9. `zhihu draft create` invokes the Wechatsync create path exactly once. Success writes a mode-`0600` receipt. An ambiguous result writes `RESULT_UNKNOWN` and must never be retried automatically. It creates a review draft, not final publish.

`ChatPost 0.1.x` has **no final-publish command** and no article-update command.

## ChatUp / ChatBrowser Boundary

Prepare machine-level artifacts explicitly through ChatUp:

```bash
chatup nodejs -I
chatup playwright install 1.61.1 --browser chromium --output json -I
chatup playwright doctor 1.61.1 --browser chromium --output json -I
```

ChatPost depends on `chatup>=0.2.4,<0.3.0`, `chatbrowser>=0.1.2,<0.2.0`, and `qrcode[pil]>=7.4,<9.0`. The current Zhihu draft route still resolves the exact browser through ChatUp, then ChatPost owns the Profile, extension, loopback CDP/bridge, QR/link handoff artifacts, and Wechatsync process. The account registry stores only non-sensitive alias metadata. ChatBrowser owns the browser runtime, Profile metadata, and CDP session metadata safety boundary; richer session discovery should come through ChatBrowser rather than storing browser secrets in ChatPost.

```python
from chatup.playwright import resolve

installation = resolve("1.61.1", browser="chromium")
```

Ownership:

- ChatUp: the Playwright package, its declared browser revision, installation metadata, and executable path;
- ChatBrowser: browser runtime, Profile metadata, and CDP session metadata;
- ChatPost: account aliases, QR image artifacts, publishing task orchestration, Profile/extension/CDP/bridge/Wechatsync one-shot tasks, and receipts;
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
