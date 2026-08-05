# CLI Tree

`ChatPost 0.1.x` now exposes two layers: common task-oriented commands for daily use, and the lower-level `zhihu` runner commands for diagnostics and compatibility. Final publish is still not implemented; the verified write path is creating a Zhihu review draft.

## Current Commands

```text
chatpost
├── --help
├── --version
├── account                         # non-sensitive account alias registry
│   ├── list                         # list configured account aliases
│   └── show                         # inspect one account alias
├── login                           # login status and manual login checkpoint
│   ├── status                       # read-only auth check
│   ├── qr                           # open login/QR checkpoint and wait for READY
│   └── code                         # open SMS-code checkpoint and wait for READY; no phone/code args
├── post                            # review-draft post entrypoint
│   └── draft                        # create one platform review draft; not final publish
└── zhihu                           # lower-level Zhihu runner compatibility layer
    ├── preflight
    ├── login
    ├── auth
    └── draft
        ├── dry-run
        └── create
```

Inspect the real help:

```bash
chatpost --help
chatpost account --help
chatpost login --help
chatpost post --help
chatpost zhihu --help
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

Then use the common entrypoints:

```bash
chatpost account list \
  --registry accounts.toml \
  --output json \
  -I

chatpost account show zhihu@zhihu-test \
  --registry accounts.toml \
  --output json \
  -I

chatpost login status zhihu@zhihu-test \
  --registry accounts.toml \
  --output json \
  -I

chatpost login qr zhihu@zhihu-test \
  --registry accounts.toml \
  --timeout 900 \
  --output json \
  -I

chatpost login code zhihu@zhihu-test \
  --registry accounts.toml \
  --timeout 900 \
  --output json \
  -I

chatpost post draft zhihu@zhihu-test article.md \
  --registry accounts.toml \
  --receipt receipt.json \
  --output json \
  -I
```

These common commands are ChatPost orchestration only:

1. `account list/show` read the account alias registry only. They do not store or print cookies, local storage, tokens, passwords, credentials, or other secrets.
2. `login status` resolves `platform@alias` and runs one read-only Zhihu auth check.
3. `login qr` opens the QR login checkpoint and waits until the account becomes `READY`; the browser/Profile still owns login state and ChatPost never exports cookies.
4. `login code` opens an SMS-code login checkpoint and waits for `READY`; phone numbers and verification codes are used only in the human browser flow, never as CLI arguments and never in the registry, config, receipt, or logs.
5. `post draft` creates one review draft and writes a mode-`0600` receipt. It is the current safe acceptance path for “posting”; it is not final publish.

## Lower-Level Zhihu Runner Commands

```bash
chatpost zhihu preflight \
  --config runner.toml \
  --output json \
  -I

chatpost zhihu login \
  --config runner.toml \
  --timeout 900 \
  --output json \
  -I

chatpost zhihu auth \
  --config runner.toml \
  --output json \
  -I

chatpost zhihu draft dry-run article.md \
  --config runner.toml \
  --output json \
  -I

chatpost zhihu draft create article.md \
  --config runner.toml \
  --receipt receipt.json \
  --output json \
  -I
```

The five lower-level gates have separate responsibilities:

1. `preflight` read-only checks the exact Playwright install, Profile permissions, extension, Node, Wechatsync CLI, secret file, and loopback ports. It does not install, launch, or write to Zhihu.
2. `login` keeps one browser/Profile alive, opens the Zhihu login page, and polls read-only auth. It is the manual QR/code checkpoint and writes no article. In the common surface, `login code` only selects the SMS-code checkpoint and stores no phone number or verification code.
3. `auth` starts the same Runner, performs one read-only Wechatsync Zhihu login check, and gracefully stops the browser.
4. `draft dry-run` parses the article without starting a browser, connecting the extension, or writing to Zhihu.
5. `draft create` invokes the Wechatsync create path exactly once. Success writes a mode-`0600` receipt. An ambiguous result writes `RESULT_UNKNOWN` and must never be retried automatically.

`ChatPost 0.1.x` has **no final-publish command** and no article-update command.

## ChatUp / ChatBrowser Boundary

Prepare machine-level artifacts explicitly through ChatUp:

```bash
chatup nodejs -I
chatup playwright install 1.61.1 --browser chromium --output json -I
chatup playwright doctor 1.61.1 --browser chromium --output json -I
```

ChatPost depends on `chatup>=0.2.4,<0.3.0` and `chatbrowser>=0.1.2,<0.2.0`. The current Zhihu draft route still resolves the exact browser through ChatUp, then ChatPost owns the Profile, extension, loopback CDP/bridge, and Wechatsync process. The account registry stores only non-sensitive alias metadata. ChatBrowser owns the browser runtime, Profile metadata, and CDP session metadata safety boundary; richer session discovery should come through ChatBrowser rather than storing browser secrets in ChatPost.

```python
from chatup.playwright import resolve

installation = resolve("1.61.1", browser="chromium")
```

Ownership:

- ChatUp: the Playwright package, its declared browser revision, installation metadata, and executable path;
- ChatBrowser: browser runtime, Profile metadata, and CDP session metadata;
- ChatPost: account aliases, publishing task orchestration, Profile/extension/CDP/bridge/Wechatsync one-shot tasks, and receipts;
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
