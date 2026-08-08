# Quickstart: Browser Login, Zhihu Drafts, and Xiaohongshu Login

This page covers ChatPost's daily path: use the pure browser login foundation to discover Profiles, check Zhihu/Xiaohongshu web login state, open a login handoff, and log out / clear browser state; then use the separate `chatpost zhihu draft` entrypoint to dry-run or create one Zhihu draft. `login/status/logout` do not create drafts, call a publishing adapter, or read/export raw cookies, local storage, IndexedDB, sessions, or tokens. Xiaohongshu `draft` currently performs local dry-run/source validation only; create explicitly returns unsupported until an adapter is connected.

## 0. Set Variables

```bash
CHATPOST=chatpost
CHATPOST_HOME="${CHATPOST_HOME:-$HOME/.chatarch/chatpost}"
REGISTRY="${CHATPOST_ACCOUNT_REGISTRY:-$CHATPOST_HOME/accounts.toml}"
PROFILE=zhihu-personal
```

ChatPost stores local state under the ChatArch-owned state root `~/.chatarch/chatpost/` by default: the default registry is `~/.chatarch/chatpost/accounts.toml`, and later runner/Profile/receipt state should live under the same root. Use `--registry` only for an explicit override or task-local experiment; do not place the default `accounts.toml` in the repository root, current working directory, or a temporary project directory.

`accounts.toml` stores only non-sensitive Profile metadata such as alias, platform, runner_config, profile, and label. Never write cookies, local storage, QR payloads, verification codes, phone numbers, passwords, tokens, or WebSocket UUIDs into the registry, config, logs, or docs. Relative `runner_config` paths resolve from the registry directory, so the default layout keeps them inside `~/.chatarch/chatpost/` too.

## 1. Confirm CLI and Profile

```bash
"$CHATPOST" --tree

"$CHATPOST" platforms   --output json   -I

"$CHATPOST" profiles   --platform zhihu   --registry "$REGISTRY"   --output json   -I

"$CHATPOST" profiles   --platform xiaohongshu   --registry "$REGISTRY"   --output json   -I

"$CHATPOST" zhihu profiles   --registry "$REGISTRY"   --output json   -I

"$CHATPOST" xiaohongshu profiles   --registry "$REGISTRY"   --output json   -I
```

Discovery commands read only the registry. They do not start a browser or inspect login state. The equivalent real command names are `chatpost platforms`, `chatpost profiles`, `chatpost zhihu profiles`, and `chatpost xiaohongshu profiles`.

The real login-foundation command names are `chatpost zhihu status`, `chatpost zhihu login`, `chatpost zhihu logout`, `chatpost xiaohongshu status`, `chatpost xiaohongshu login`, and `chatpost xiaohongshu logout`.

## 2. Check Current Web Login State

```bash
"$CHATPOST" zhihu status "$PROFILE"   --registry "$REGISTRY"   --output json   -I
```

`status` is browser-level only: it opens/connects a controlled Chromium Profile and infers state from Zhihu page URL, DOM, and visible account entrypoints. Status values are:

- `LOGGED_IN`: page-visible state confirms login, optionally with `account_name` / `account_url`;
- `LOGGED_OUT`: page-visible state shows logged out;
- `UNKNOWN`: the page cannot be judged reliably, and ChatPost does not fall back to a publishing adapter.

## 3. Log In or Reuse an Authenticated Profile

```bash
"$CHATPOST" zhihu login "$PROFILE"   --registry "$REGISTRY"   --timeout 900   --output json   -I
```

Contract:

- Already logged in: browser-page status runs first and returns `LOGGED_IN`; no QR or login link is emitted.
- Logged out: ChatPost opens Zhihu's login page in the same Profile, quickly emits a page-owned `login_url` or `browser_opened` handoff, then keeps the browser alive while a human completes login.
- No cookies, local storage, IndexedDB, sessions, or tokens are read/exported.
- No publishing adapter, adapter env, or publishing token is required.
- Screenshots are not login handoff and must not masquerade as final output.
- Sliders, phone numbers, and verification codes are human browser-flow inputs; the CLI has no `--phone`, `--code`, `--otp`, or `--sms-code` options.

JSON output is JSON Lines: one interactive handoff event first, then a final login-completed or timeout event.

## 4. Read Back Status

```bash
"$CHATPOST" zhihu status "$PROFILE"   --registry "$REGISTRY"   --output json   -I
```

After a real login practice, this should return `LOGGED_IN`, ideally with page-visible `account_name` or `account_url`.

## 5. Log Out / Clear State

```bash
"$CHATPOST" zhihu logout "$PROFILE"   --registry "$REGISTRY"   --output json   -I
```

`logout` first runs browser-level status. It returns `ALREADY_LOGGED_OUT` when already logged out, and clears Zhihu origins only after a logged-in precheck. Clearing state is a browser command; it does not read session values.

## 5b. Xiaohongshu Login Link Handoff

Xiaohongshu keeps the same platform shape as Zhihu. `login` opens the Xiaohongshu login page and tries to extract a page-owned `login_url` from the page QR code, BarcodeDetector, or page resources. If the page does not expose a decodable QR/login URL, ChatPost returns `browser_opened` and the human completes login in the browser. If Xiaohongshu marks the current network as risky, the CLI returns `LOGIN_BLOCKED` / `block_reason=network_risk` instead of pretending that a fallback login page is a QR URL.

```bash
XHS_PROFILE=xhs-personal
"$CHATPOST" xiaohongshu status "$XHS_PROFILE"   --registry "$REGISTRY"   --output json   -I
"$CHATPOST" xiaohongshu login "$XHS_PROFILE"   --registry "$REGISTRY"   --timeout 900   --output json   -I
"$CHATPOST" xiaohongshu logout "$XHS_PROFILE"   --registry "$REGISTRY"   --output json   -I
```

Xiaohongshu draft currently performs local validation only and does not write remotely; the literal command name is `chatpost xiaohongshu draft`:

```bash
"$CHATPOST" xiaohongshu draft "$XHS_PROFILE" /absolute/path/to/note.md   --registry "$REGISTRY"   --dry-run   --output json   -I
```

## Common Stops

| Stop | Handling |
| --- | --- |
| `login` returns `LOGGED_IN` immediately | Expected: the Profile is already logged in. |
| `login` emits `browser_opened` but no page-owned `login_url` | The browser is open for human login; do not use screenshots or private artifacts as login links. |
| The login page asks for a slider or verification code | Stay in the human browser flow; do not put codes into CLI args or logs. |
| `login` returns `LOGIN_BLOCKED` / `block_reason=network_risk` | The current egress was rejected by the platform, so no scannable QR can be generated; retry from a trusted network or local browser Profile. |
| `status` returns `UNKNOWN` | Report unknown only; do not fall back to an adapter or read cookies/tokens. |

## 6. Draft dry-run and create through Wechatsync

`chatpost zhihu draft` is intentionally separate from the browser-level login commands. It reuses the same registry alias and runner config, but it loads the full runner fields for Wechatsync, extension, bridge, and private env file only inside the draft flow. `login/status/logout` must continue to use `load_browser_config` and must not require adapter readiness.

Dry-run validates the source without starting a browser or writing a draft:

```bash
ARTICLE=/absolute/path/to/article.md
chatpost zhihu draft zhihu-practice-quickstart "$ARTICLE" \
  --registry /home/zhihong/Playground/projects/chatarch/08-05-chatpost-login-cli-practice/playground/quickstart-practice-20260807-182534/accounts.toml \
  --dry-run \
  --output json \
  -I
```

A real create requires an explicit receipt path and creates exactly one Zhihu draft. It does not final-publish:

```bash
RECEIPT=~/.chatarch/chatpost/runners/zhihu-practice-quickstart/run/zhihu-draft-receipt.json
chatpost zhihu draft zhihu-practice-quickstart "$ARTICLE" \
  --registry /home/zhihong/Playground/projects/chatarch/08-05-chatpost-login-cli-practice/playground/quickstart-practice-20260807-182534/accounts.toml \
  --receipt "$RECEIPT" \
  --output json \
  -I
```

Expected successful statuses are `DRY_RUN_OK` for dry-run and `DRAFT_CREATED` for create. Create writes a mode `0600` receipt with the draft id, `/edit` review URL, source digest, and cleanup statuses. If the create path returns `RESULT_UNKNOWN`, do not retry automatically; inspect the receipt and the browser before deciding next steps.
