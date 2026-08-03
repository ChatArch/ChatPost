# CLI Tree

`ChatPost 0.1.0` first ships one task-oriented Zhihu draft route. Generic `runner`, `account`, `publication`, and article-update commands remain future design and are not current interfaces.

## Current Commands

```text
chatpost
├── --help
├── --version
└── zhihu
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
chatpost zhihu --help
chatpost zhihu draft --help
```

## Task Order

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

The five gates have separate responsibilities:

1. `preflight` read-only checks the exact Playwright install, Profile permissions, extension, Node, Wechatsync CLI, secret file, and loopback ports. It does not install, launch, or write to Zhihu.
2. `login` keeps one browser/Profile alive, opens the Zhihu login page, and polls read-only auth. It is the manual QR/code checkpoint and writes no article.
3. `auth` starts the same Runner, performs one read-only Wechatsync Zhihu login check, and gracefully stops the browser.
4. `draft dry-run` parses the article without starting a browser, connecting the extension, or writing to Zhihu.
5. `draft create` invokes the Wechatsync create path exactly once. Success writes a mode-`0600` receipt. An ambiguous result writes `RESULT_UNKNOWN` and must never be retried automatically.

`ChatPost 0.1.0` has **no final-publish command** and no article-update command.

## ChatUp Boundary

Prepare machine-level artifacts explicitly through ChatUp:

```bash
chatup nodejs -I
chatup playwright install 1.61.1 --browser chromium --output json -I
chatup playwright doctor 1.61.1 --browser chromium --output json -I
```

ChatPost depends on `chatup>=0.2.4,<0.3.0` and only calls:

```python
from chatup.playwright import resolve

installation = resolve("1.61.1", browser="chromium")
```

Ownership:

- ChatUp: the Playwright package, its declared browser revision, installation metadata, and executable path;
- ChatPost: the persistent Profile, extension, CDP, loopback bridge, Wechatsync process, one-shot task, and receipt;
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
account add|login|status
publication list|show|retry
article update
```

Until implementation and tests exist, they must remain explicitly marked as proposals and stay out of executable Quick Starts.
