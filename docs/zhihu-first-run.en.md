# Zhihu First Setup and Draft Acceptance

This is the executable `ChatPost 0.1.0` Quick Start. It reproduces the verified Playwright-cache + Profile + Wechatsync route while separating artifact and task ownership between ChatUp and ChatPost.

## Boundary

```text
ChatUp 0.2.4
  -> install exact Playwright package + browser revision
  -> chatup.playwright.resolve(...)

ChatPost 0.1.0
  -> persistent Profile + browser lifecycle
  -> exact extension + loopback CDP/bridge
  -> login checkpoint / auth / dry-run / one create / receipt

Wechatsync
  -> Zhihu adapter and draft write
```

The route is user-level, Docker-free, and root-free. It never reads or exports cookies/local storage, creates drafts only, never clicks final publish, never retries `RESULT_UNKNOWN`, and does not yet implement same-ID update.

## 1. Install Python Packages

```bash
python3 -m venv "$HOME/.chatarch/venvs/chatpost"
"$HOME/.chatarch/venvs/chatpost/bin/python" -m pip install --upgrade pip
"$HOME/.chatarch/venvs/chatpost/bin/python" -m pip install \
  "chatup==0.2.4" \
  "chatpost==0.1.0"

CHATUP="$HOME/.chatarch/venvs/chatpost/bin/chatup"
CHATPOST="$HOME/.chatarch/venvs/chatpost/bin/chatpost"
"$CHATUP" --version
"$CHATPOST" --version
```

## 2. Prepare Node.js and the Playwright Browser

```bash
"$CHATUP" nodejs -I
# Refresh the shell as instructed by ChatUp, then verify Node/npm.
node --version
npm --version

"$CHATUP" playwright install 1.61.1 \
  --browser chromium \
  --output json \
  -I
"$CHATUP" playwright doctor 1.61.1 \
  --browser chromium \
  --output json \
  -I
```

ChatUp installs under `~/.chatarch/playwright/1.61.1/`. ChatPost only resolves that installation and never downloads or upgrades implicitly.

Task-verified combination:

```text
Playwright package  1.61.1
browser             chromium
revision            1228
Chrome for Testing  149.0.7827.55
```

## 3. Prepare the Wechatsync Adapter

```bash
git clone https://github.com/ChatArch/Wechatsync.git "$HOME/.chatarch/src/Wechatsync"
cd "$HOME/.chatarch/src/Wechatsync"
git checkout 0073787cfbff0f7af4d1b427da3adbb16d92eeb8
corepack enable
pnpm install --frozen-lockfile
pnpm build

test -f packages/cli/dist/index.js
test -f packages/extension/dist/manifest.json
```

ChatPost orchestrates Wechatsync's CLI, extension, and receipt. It does not copy the Zhihu adapter business logic.

## 4. Create the Profile and Private Bridge Environment

```bash
RUNNER_HOME="$HOME/.chatarch/chatpost/runners/zhihu-primary"
install -d -m 700 "$RUNNER_HOME/profile"
install -d -m 700 "$RUNNER_HOME/run"
```

Generate a local bridge token without printing it:

```bash
RUNNER_HOME="$RUNNER_HOME" python3 - <<'PY'
import os
import secrets
from pathlib import Path

path = Path(os.environ["RUNNER_HOME"]) / "bridge.env"
path.write_text(
    "WECHATSYNC_TOKEN=" + secrets.token_urlsafe(32) + "\n",
    encoding="utf-8",
)
path.chmod(0o600)
PY
```

The bridge token authenticates only the local extension/CLI and is not a Zhihu password. Never commit or document the env, Profile, cookies, local storage, QR content, or verification codes.

## 5. Write Runner TOML

Copy `examples/zhihu/runner.toml.example` to `$RUNNER_HOME/runner.toml`, set mode `0600`, and replace all paths with absolute paths on the current machine.

```toml
[zhihu]
playwright_version = "1.61.1"
playwright_home = "/home/user/.chatarch/playwright"
profile_dir = "/home/user/.chatarch/chatpost/runners/zhihu-primary/profile"
extension_dir = "/home/user/.chatarch/src/Wechatsync/packages/extension/dist"
node_bin = "/absolute/path/to/node"
wechatsync_cli = "/home/user/.chatarch/src/Wechatsync/packages/cli/dist/index.js"
env_file = "/home/user/.chatarch/chatpost/runners/zhihu-primary/bridge.env"
cdp_host = "127.0.0.1"
cdp_port = 9227
bridge_host = "127.0.0.1"
bridge_port = 9527
extension_id = "dipgimoobbhdefncjomgehikkbaklgii"
headless = true
browser_args = ["--disable-dev-shm-usage"]
```

macOS normally uses an empty `browser_args` list. Add Linux arguments only when real smoke evidence requires them. Never expose ports or weaken the ownership boundary by default.

## 6. Static Preflight

```bash
"$CHATPOST" zhihu preflight \
  --config "$RUNNER_HOME/runner.toml" \
  --output json \
  -I
```

Continue only on `status=READY`. Preflight checks the exact ChatUp installation, Profile and secret permissions, Node, the Wechatsync CLI and extension manifest, a present token without printing it, and unused loopback-only CDP/bridge ports.

## 7. Manual First Login

Check an existing Profile first:

```bash
"$CHATPOST" zhihu auth \
  --config "$RUNNER_HOME/runner.toml" \
  --output json \
  -I
```

If logged out, start the checkpoint:

```bash
"$CHATPOST" zhihu login \
  --config "$RUNNER_HOME/runner.toml" \
  --timeout 900 \
  --output json \
  -I
```

`login` keeps the same browser/Profile open, opens Zhihu sign-in, and polls read-only auth until it returns `READY`. Set `headless=false` on a machine with a display. A server needs an explicitly authorized local-only display/tunnel or controlled screenshot route; never expose CDP, VNC, or bridge publicly.

Run `auth` once more after login. ChatPost never reads cookies from the Profile.

## 8. Dry Run

```bash
ARTICLE=/absolute/path/to/article.md
"$CHATPOST" zhihu draft dry-run "$ARTICLE" \
  --config "$RUNNER_HOME/runner.toml" \
  --output json \
  -I
```

Confirm the title, body, asset references, and fixed marker from the JSON `preview` field. The preview is capped at 8,000 characters and redacts values resolved from the private env. Dry-run starts no browser, connects no extension, and writes nothing to Zhihu.

## 9. Create Exactly One Draft

```bash
RECEIPT="$RUNNER_HOME/run/zhihu-draft-receipt.json"
"$CHATPOST" zhihu draft create "$ARTICLE" \
  --config "$RUNNER_HOME/runner.toml" \
  --receipt "$RECEIPT" \
  --output json \
  -I
```

Acceptance requires `DRAFT_CREATED`, a draft ID and `/edit` review URL, a mode-`0600` receipt, editor-page readback of the expected title and marker, and no final publish.

Each browser startup creates a random `data:text/plain,chatpost-run-*` marker. ChatPost binds CDP to the spawned process only after the configured loopback port exposes both that marker and the corresponding browser WebSocket UUID.

Normal cleanup sends CDP `Browser.close` to the browser WebSocket endpoint captured at startup. It does not rediscover whichever browser might later occupy the same port, and it sends no process termination signal. If the draft result is already definitive but cleanup fails, the receipt keeps `DRAFT_CREATED` and adds `cleanup_status=MANUAL_RECOVERY_REQUIRED`. Recover the process manually and do not run create again. For browser startup failures, ChatPost waits for stderr drain and returns only bounded diagnostics with Profile paths, private env values, and the run marker redacted.

The `RESULT_UNKNOWN` receipt also records `cleanup_status` and includes `cleanup_error` when manual recovery is required. This applies both to a non-zero adapter exit and to a successful exit without a review URL. Browser endpoints, tokens, and connection details are never written to the receipt.

Image-upload failure can coexist with successful draft creation. Report the actual editor content; exit code zero alone does not prove image completeness.

## 10. Ambiguity Recovery

For `{"status":"RESULT_UNKNOWN"}`, stop automation immediately. Do not run create again. Inspect the same account's draft box by title, marker, and time, then record the unique draft ID/review URL or make a human decision before any new create.

## Repository Collaboration

- ChatUp provides only the Playwright package/browser substrate. It creates no Profile, launches no browser, and knows nothing about Zhihu.
- ChatPost owns Profile/process/CDP/bridge/login checkpoint/one-shot write/receipt. It duplicates no Playwright download logic and reads no login database.
- Wechatsync is the Zhihu adapter. Protocol changes are handled explicitly at ChatPost's adapter boundary.
- Article update needs separate acceptance based on a stored draft/article ID. Title matching or another create is not update.
